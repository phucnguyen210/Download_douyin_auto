from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional, Any

from openai import AsyncOpenAI
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.logger import setup_logger
from app.utils import ensure_dir
from app.utils.ffmpeg_utils import run_ffmpeg_command, resolve_ffmpeg_path, validate_audio_file


ASR_API_LIMIT_BYTES = 25 * 1024 * 1024
SAFE_ASR_UPLOAD_BYTES = 23 * 1024 * 1024
DEFAULT_CHUNK_SECONDS = 600
MIN_CHUNK_SECONDS = 60


class ASRService:
    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("asr")
        self.client: Optional[AsyncOpenAI] = None
        if self.settings.openai_api_key:
            self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.ffmpeg = resolve_ffmpeg_path(settings.ffmpeg_path)
        self._sem = asyncio.Semaphore(2)

    async def transcribe(self, audio_path: Path) -> dict[str, Any]:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        async with self._sem:
            if self.client:
                return await self._transcribe_with_openai(audio_path)
            txt = f"[DUMMY TRANSCRIPT] {audio_path.name}"
            return {"text": txt, "segments": []}

    async def _transcribe_with_openai(self, audio_path: Path) -> dict[str, Any]:
        chunks = self._prepare_upload_files(audio_path)
        if len(chunks) > 1:
            self.logger.info(f"ASR audio was split into {len(chunks)} chunk(s) to stay under the upload limit.")

        texts: list[str] = []
        segments: list[dict[str, Any]] = []
        offset = 0.0
        for index, chunk_path in enumerate(chunks, start=1):
            size = chunk_path.stat().st_size
            if size >= ASR_API_LIMIT_BYTES:
                raise RuntimeError(
                    f"ASR chunk is still too large: {chunk_path} "
                    f"({size} bytes, limit {ASR_API_LIMIT_BYTES} bytes)."
                )
            self.logger.info(f"ASR chunk {index}/{len(chunks)}: {chunk_path.name} ({size} bytes)")
            result = await self._transcribe_single_with_openai(chunk_path)
            text = str(result.get("text", "")).strip()
            if text:
                texts.append(text)
            for seg in result.get("segments", []) or []:
                try:
                    start = float(seg.get("start", 0.0)) + offset
                    end = float(seg.get("end", start)) + offset
                except Exception:
                    continue
                seg_text = str(seg.get("text", "")).strip()
                if seg_text:
                    segments.append({"start": start, "end": end, "text": seg_text})
            offset += self._probe_duration_seconds(chunk_path)

        return {"text": "\n".join(texts).strip(), "segments": segments}

    async def _transcribe_single_with_openai(self, audio_path: Path) -> dict[str, Any]:
        last_err = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=12),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    with audio_path.open("rb") as fh:
                        response = await self.client.audio.transcriptions.create(
                            file=fh,
                            model=self.settings.openai_asr_model,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"],
                        )
                    return self._response_to_transcript(response)
                except TypeError:
                    with audio_path.open("rb") as fh:
                        response = await self.client.audio.transcriptions.create(
                            file=fh,
                            model=self.settings.openai_asr_model,
                            response_format="verbose_json",
                        )
                    return self._response_to_transcript(response)
                except Exception as exc:
                    last_err = exc
                    self.logger.warning(f"ASR error (will retry): {type(exc).__name__}: {exc}")
                    raise
        if last_err:
            raise last_err
        raise RuntimeError("ASR failed")

    def _prepare_upload_files(self, audio_path: Path) -> list[Path]:
        size = audio_path.stat().st_size
        if size <= SAFE_ASR_UPLOAD_BYTES:
            return [audio_path]

        self.logger.info(
            f"Audio file is {size} bytes, larger than safe ASR upload size "
            f"{SAFE_ASR_UPLOAD_BYTES} bytes. Creating compressed chunks."
        )

        segment_seconds = DEFAULT_CHUNK_SECONDS
        while segment_seconds >= MIN_CHUNK_SECONDS:
            chunks = self._create_compressed_chunks(audio_path, segment_seconds)
            oversized = [p for p in chunks if p.stat().st_size > SAFE_ASR_UPLOAD_BYTES]
            if chunks and not oversized:
                return chunks
            segment_seconds //= 2
            self.logger.info(f"ASR chunk still too large; retrying with {segment_seconds}s segments.")

        raise RuntimeError(
            f"Could not create ASR chunks under {SAFE_ASR_UPLOAD_BYTES} bytes for {audio_path}."
        )

    def _create_compressed_chunks(self, audio_path: Path, segment_seconds: int) -> list[Path]:
        chunk_dir = audio_path.parent / f"{audio_path.stem}_asr_chunks"
        ensure_dir(chunk_dir)
        for old_chunk in chunk_dir.glob("chunk_*.mp3"):
            old_chunk.unlink()

        output_pattern = chunk_dir / "chunk_%03d.mp3"
        command = [
            self.ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            str(output_pattern),
        ]
        run_ffmpeg_command(command, timeout=1800)

        chunks = sorted(chunk_dir.glob("chunk_*.mp3"))
        chunks = [p for p in chunks if validate_audio_file(p)]
        if not chunks:
            raise RuntimeError(f"FFmpeg did not create ASR chunks for {audio_path}.")
        return chunks

    def _probe_duration_seconds(self, media_path: Path) -> float:
        try:
            from app.utils.media_utils import get_audio_duration

            return float(get_audio_duration(media_path))
        except Exception:
            return 0.0

    @staticmethod
    def _response_to_transcript(response) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            data = response.model_dump()
        elif isinstance(response, dict):
            data = response
        else:
            data = {"text": getattr(response, "text", str(response))}

        text = str(data.get("text") or "")
        raw_segments = data.get("segments") or []
        segments: list[dict[str, Any]] = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                if hasattr(seg, "model_dump"):
                    seg = seg.model_dump()
                else:
                    continue
            seg_text = str(seg.get("text", "")).strip()
            if not seg_text:
                continue
            segments.append({
                "start": float(seg.get("start", 0.0) or 0.0),
                "end": float(seg.get("end", 0.0) or 0.0),
                "text": seg_text,
            })
        return {"text": text, "segments": segments}

    @staticmethod
    def write_transcript_files(base_path: Path, transcript: str | dict[str, Any]) -> tuple[Path, Path]:
        base_path = Path(base_path)
        ensure_dir(base_path.parent)
        json_path = base_path.with_suffix(".transcript.json")
        srt_path = base_path.with_suffix(".transcript.srt")
        if isinstance(transcript, dict):
            data = {
                "text": str(transcript.get("text", "")),
                "segments": transcript.get("segments") or [],
            }
        else:
            data = {"text": str(transcript), "segments": []}
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        srt_content = ASRService.segments_to_srt(data.get("segments") or [], data.get("text", ""))
        with srt_path.open("w", encoding="utf-8") as f:
            f.write(srt_content)
        return json_path, srt_path

    @staticmethod
    def segments_to_srt(segments: list[dict[str, Any]], fallback_text: str = "") -> str:
        def fmt(seconds: float) -> str:
            seconds = max(0.0, float(seconds or 0.0))
            ms_total = int(round(seconds * 1000))
            h, rem = divmod(ms_total, 3600_000)
            m, rem = divmod(rem, 60_000)
            s, ms = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        if not segments:
            text = (fallback_text or "").strip()
            if not text:
                return ""
            return f"1\n00:00:00,000 --> 00:00:10,000\n{text}\n"

        parts: list[str] = []
        for idx, seg in enumerate(segments, start=1):
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start + 0.1) or start + 0.1)
            if end <= start:
                end = start + 0.1
            parts.extend([str(idx), f"{fmt(start)} --> {fmt(end)}", text, ""])
        return "\n".join(parts)
