from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.logger import setup_logger
from app.utils.ffmpeg_utils import run_ffmpeg_command, resolve_ffmpeg_path
from app.utils.media_utils import get_audio_duration
from app.utils import ensure_dir

TTS_VOICE_OPTIONS: dict[str, dict[str, str]] = {
    "OpenAI nova": {"provider": "openai", "voice": "nova"},
    "OpenAI alloy": {"provider": "openai", "voice": "alloy"},
    "OpenAI shimmer": {"provider": "openai", "voice": "shimmer"},
    "OpenAI echo": {"provider": "openai", "voice": "echo"},
    "OpenAI onyx": {"provider": "openai", "voice": "onyx"},
    "OpenAI fable": {"provider": "openai", "voice": "fable"},
    "OpenAI ash": {"provider": "openai", "voice": "ash"},
    "OpenAI coral": {"provider": "openai", "voice": "coral"},
    "OpenAI sage": {"provider": "openai", "voice": "sage"},
    "OpenAI verse": {"provider": "openai", "voice": "verse"},
    "Edge HoaiMy free vi-VN": {"provider": "edge", "voice": "vi-VN-HoaiMyNeural"},
    "Edge NamMinh free vi-VN": {"provider": "edge", "voice": "vi-VN-NamMinhNeural"},
    "gTTS free Vietnamese": {"provider": "gtts", "voice": "vi"},
}
DEFAULT_TTS_VOICE_LABEL = "OpenAI nova"


def resolve_tts_voice(label: str | None = None) -> tuple[str, str, str]:
    selected = (label or "").strip()
    if selected in TTS_VOICE_OPTIONS:
        item = TTS_VOICE_OPTIONS[selected]
        return item["provider"], item["voice"], selected

    provider = (os.getenv("TTS_PROVIDER", "openai") or "openai").strip().lower()
    if provider == "edge":
        voice = (os.getenv("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural") or "vi-VN-HoaiMyNeural").strip()
    elif provider == "gtts":
        voice = "vi"
    else:
        provider = "openai"
        voice = (os.getenv("OPENAI_TTS_VOICE", "nova") or "nova").strip()

    for option_label, item in TTS_VOICE_OPTIONS.items():
        if item["provider"] == provider and item["voice"] == voice:
            return provider, voice, option_label
    return provider, voice, f"{provider}:{voice}"

class TTSService:
    def __init__(self, settings: Settings, logger=None, provider: str | None = None, voice: str | None = None, voice_label: str | None = None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("tts")
        self.ffmpeg = resolve_ffmpeg_path(settings.ffmpeg_path)
        self.openai_tts_model = os.getenv("OPENAI_TTS_MODEL", "tts-1").strip() or "tts-1"
        resolved_provider, resolved_voice, resolved_label = resolve_tts_voice(voice_label)
        self.tts_provider = (provider or resolved_provider).strip().lower()
        self.tts_voice = (voice or resolved_voice).strip()
        self.tts_voice_label = resolved_label if not voice else f"{self.tts_provider}:{self.tts_voice}"
        self.openai_tts_voice = self.tts_voice if self.tts_provider == "openai" else (os.getenv("OPENAI_TTS_VOICE", "nova").strip() or "nova")
        self.edge_tts_voice = self.tts_voice if self.tts_provider == "edge" else (os.getenv("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural").strip() or "vi-VN-HoaiMyNeural")
        self.openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.sync_mode = (os.getenv("TTS_SYNC_MODE", "balanced") or "balanced").strip().lower()
        self.start_offset_seconds = self._env_float("TTS_START_OFFSET_MS", 250.0) / 1000.0
        self.max_block_chars = int(os.getenv("TTS_BLOCK_MAX_CHARS", "320") or "320")
        self.max_speed = max(1.0, self._env_float("TTS_MAX_SPEED", 1.8))
        self.min_slot_seconds = max(0.1, self._env_float("TTS_MIN_SLOT_SECONDS", 0.35))

    def synthesize_from_text(self, text: str, out_path: Path) -> Path:
        out_path = Path(out_path)
        ensure_dir(out_path.parent)
        text = (text or "").strip()
        if not text:
            return self._create_silence(out_path, 0.2)

        errors: list[str] = []
        if self.tts_provider == "openai":
            if self.openai_client:
                try:
                    return self._synthesize_with_openai(text, out_path)
                except Exception as exc:
                    errors.append(f"OpenAI TTS: {exc}")
                    self.logger.warning(f"OpenAI TTS failed, trying fallback if available: {exc}")
            else:
                errors.append("OpenAI TTS: missing OPENAI_API_KEY")

        if self.tts_provider == "edge":
            try:
                return self._synthesize_with_edge_tts(text, out_path)
            except Exception as exc:
                errors.append(f"Edge TTS: {exc}")
                self.logger.warning(f"Edge TTS failed, trying fallback if available: {exc}")

        try:
            return self._synthesize_with_gtts(text, out_path)
        except Exception as exc:
            errors.append(f"gTTS: {exc}")

        raise RuntimeError("Vietnamese TTS failed for text segment. " + " | ".join(errors))

    def _synthesize_with_openai(self, text: str, out_path: Path) -> Path:
        tmp_audio = out_path.with_suffix(".openai_tts.mp3")
        response = self.openai_client.audio.speech.create(
            model=self.openai_tts_model,
            voice=self.openai_tts_voice,
            input=text,
            response_format="mp3",
        )
        response.write_to_file(tmp_audio)
        self._convert_to_wav(tmp_audio, out_path)
        tmp_audio.unlink(missing_ok=True)
        return out_path

    def _synthesize_with_edge_tts(self, text: str, out_path: Path) -> Path:
        import edge_tts

        tmp_mp3 = out_path.with_suffix(".edge_tts.mp3")

        async def _save() -> None:
            communicate = edge_tts.Communicate(text=text, voice=self.edge_tts_voice)
            await communicate.save(str(tmp_mp3))

        asyncio.run(_save())
        self._convert_to_wav(tmp_mp3, out_path)
        tmp_mp3.unlink(missing_ok=True)
        return out_path

    def _synthesize_with_gtts(self, text: str, out_path: Path) -> Path:
        from gtts import gTTS

        tmp_mp3 = out_path.with_suffix(".gtts.mp3")
        tts = gTTS(text=text, lang="vi")
        tts.save(str(tmp_mp3))
        self._convert_to_wav(tmp_mp3, out_path)
        tmp_mp3.unlink(missing_ok=True)
        return out_path

    def _convert_to_wav(self, input_path: Path, out_path: Path) -> None:
        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ]
        run_ffmpeg_command(cmd, timeout=300)

    def synthesize_from_segments(self, segments: list[dict[str, Any]], out_path: Path) -> Path:
        out_path = Path(out_path)
        ensure_dir(out_path.parent)
        work_dir = out_path.parent / f"{out_path.stem}_segments"
        ensure_dir(work_dir)
        for old_file in work_dir.glob("*.wav"):
            old_file.unlink()
        for old_file in work_dir.glob("*.mp3"):
            old_file.unlink()
        list_file = work_dir / "concat.txt"
        list_file.unlink(missing_ok=True)

        pieces: list[Path] = []
        cursor = 0.0
        clean_segments = self._clean_segments(segments)
        if not clean_segments:
            raise RuntimeError("Transcript has no non-empty TTS segments.")

        units = clean_segments if self.sync_mode == "strict" else self._group_segments_for_tts(clean_segments)
        if self.sync_mode == "strict" and len(units) > 120:
            self.logger.warning(
                "Strict TTS is slow: %s TTS requests will be generated. Set TTS_SYNC_MODE=balanced for faster processing.",
                len(units),
            )
        total = len(units)
        self.logger.info(
            "TTS sync mode=%s, units=%s, offset=%.3fs, max_speed=%.2f",
            self.sync_mode,
            total,
            self.start_offset_seconds,
            self.max_speed,
        )

        for index, unit in enumerate(units, start=1):
            target_start = max(0.0, float(unit["start"]) + self.start_offset_seconds)
            target_duration = max(
                self.min_slot_seconds,
                float(unit.get("end", unit["start"]) or unit["start"]) - float(unit["start"]),
            )
            text = str(unit["text"]).strip()
            gap = max(0.0, target_start - cursor)
            if gap >= 0.03:
                silence_path = work_dir / f"{index:04d}_silence.wav"
                self._create_silence(silence_path, gap)
                pieces.append(silence_path)
                cursor += gap

            raw_voice_path = work_dir / f"{index:04d}_voice_raw.wav"
            voice_path = work_dir / f"{index:04d}_voice.wav"
            self.logger.info(
                "TTS unit %s/%s: start=%.3f slot=%.3f chars=%s | %s",
                index,
                total,
                target_start,
                target_duration,
                len(text),
                text[:80],
            )
            self.synthesize_from_text(text, raw_voice_path)
            if not raw_voice_path.exists() or raw_voice_path.stat().st_size <= 0:
                raise RuntimeError(f"TTS output is empty: {raw_voice_path}")
            self._fit_voice_to_slot(raw_voice_path, voice_path, target_duration)
            pieces.append(voice_path)
            try:
                voice_duration = float(get_audio_duration(voice_path))
            except Exception:
                voice_duration = target_duration
            cursor += max(0.05, voice_duration)

        with list_file.open("w", encoding="utf-8") as f:
            for piece in pieces:
                safe_path = str(piece.resolve()).replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        cmd = [
            self.ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ]
        run_ffmpeg_command(cmd, timeout=1800)
        if not out_path.exists() or out_path.stat().st_size <= 0:
            raise RuntimeError(f"Final TTS file is empty: {out_path}")
        return out_path

    def _clean_segments(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean: list[dict[str, Any]] = []
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
            item = {
                "start": start,
                "end": end,
                "text": text,
                "speaker": seg.get("speaker") or seg.get("speaker_id") or "",
                "voice_type": seg.get("voice_type") or seg.get("gender") or "",
            }
            clean.append(item)
        return sorted(clean, key=lambda item: float(item["start"]))

    def _group_segments_for_tts(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
            speaker = str(seg.get("speaker", "") or "")
            if current is None:
                current = {"start": start, "end": end, "parts": [text], "speaker": speaker}
                continue
            candidate = " ".join([*current["parts"], text])
            gap = start - float(current["end"])
            speaker_changed = bool(speaker and current.get("speaker") and speaker != current.get("speaker"))
            if len(candidate) > self.max_block_chars or gap > 1.0 or speaker_changed:
                blocks.append({
                    "start": current["start"],
                    "end": current["end"],
                    "text": " ".join(current["parts"]),
                    "speaker": current.get("speaker", ""),
                })
                current = {"start": start, "end": end, "parts": [text], "speaker": speaker}
            else:
                current["parts"].append(text)
                current["end"] = end
        if current is not None:
            blocks.append({
                "start": current["start"],
                "end": current["end"],
                "text": " ".join(current["parts"]),
                "speaker": current.get("speaker", ""),
            })
        return blocks

    def _fit_voice_to_slot(self, input_path: Path, out_path: Path, target_duration: float) -> None:
        duration = float(get_audio_duration(input_path))
        if target_duration <= 0 or duration <= target_duration * 1.05:
            self._copy_audio(input_path, out_path)
            return

        speed = min(self.max_speed, max(1.0, duration / target_duration))
        filter_expr = self._atempo_filter(speed)
        self.logger.info(
            "Speeding TTS from %.3fs to target %.3fs with atempo %.3f",
            duration,
            target_duration,
            speed,
        )
        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            filter_expr,
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ]
        run_ffmpeg_command(cmd, timeout=300)

    def _copy_audio(self, input_path: Path, out_path: Path) -> None:
        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out_path),
        ]
        run_ffmpeg_command(cmd, timeout=120)

    @staticmethod
    def _atempo_filter(speed: float) -> str:
        factors: list[float] = []
        remaining = max(0.5, speed)
        while remaining > 2.0:
            factors.append(2.0)
            remaining /= 2.0
        while remaining < 0.5:
            factors.append(0.5)
            remaining /= 0.5
        factors.append(remaining)
        return ",".join(f"atempo={factor:.4f}" for factor in factors)

    def _create_silence(self, out_path: Path, duration: float) -> Path:
        out_path = Path(out_path)
        ensure_dir(out_path.parent)
        cmd = [
            self.ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000",
            "-t",
            f"{max(0.03, duration):.3f}",
            str(out_path),
        ]
        run_ffmpeg_command(cmd)
        return out_path

    def synthesize_from_transcript_file(self, transcript_json: Path, out_path: Path) -> Path:
        transcript_json = Path(transcript_json)
        if not transcript_json.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_json}")
        with transcript_json.open("r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments") or []
        if segments:
            self._assert_not_untranslated_cjk(
                "\n".join(str(seg.get("text", "") or "") for seg in segments),
                transcript_json,
            )
            return self.synthesize_from_segments(segments, out_path)
        text = str(data.get("text", "")).strip()
        if not text:
            raise RuntimeError(f"Transcript has no text for TTS: {transcript_json}")
        self._assert_not_untranslated_cjk(text, transcript_json)
        return self.synthesize_from_text(text, out_path)

    @staticmethod
    def _assert_not_untranslated_cjk(text: str, transcript_json: Path) -> None:
        compact = re.sub(r"\s+", "", text or "")
        if not compact:
            return
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", compact))
        if cjk_count >= 4 and cjk_count / max(1, len(compact)) >= 0.15:
            raise RuntimeError(
                "Transcript still contains mostly Chinese text; Vietnamese translation failed or was not used. "
                f"Stop before TTS: {transcript_json}"
            )

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            return default
