from __future__ import annotations

from pathlib import Path
import json
import math
from typing import Any, List

from app.utils.media_utils import get_audio_duration
from app.utils import ensure_dir
from app.services.asr_service import ASRService


def _format_time(seconds: float) -> str:
    ms = int((seconds - math.floor(seconds)) * 1000)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_words(text: str) -> List[str]:
    return text.strip().split()


def generate_srt_from_text(text: str, audio_duration: float, target_segment_seconds: float = 4.0) -> str:
    words = _split_words(text)
    if not words:
        return ""
    words_per_second = max(1e-6, len(words) / max(0.001, audio_duration))
    words_per_segment = max(1, int(words_per_second * target_segment_seconds))

    segments = []
    idx = 0
    total_words = len(words)
    seg_index = 1
    while idx < total_words:
        end_idx = min(total_words, idx + words_per_segment)
        seg_words = words[idx:end_idx]
        start_time = (idx / total_words) * audio_duration
        end_time = (end_idx / total_words) * audio_duration
        text_line = " ".join(seg_words)
        segments.append((seg_index, start_time, end_time, text_line))
        seg_index += 1
        idx = end_idx

    parts = []
    for si, st, et, t in segments:
        parts.append(str(si))
        parts.append(f"{_format_time(st)} --> {_format_time(et)}")
        parts.append(t)
        parts.append("")
    return "\n".join(parts)


class SubtitleService:
    @staticmethod
    def create_srt_for_transcript(transcript_json: Path, audio_path: Path, out_srt: Path) -> Path:
        transcript_json = Path(transcript_json)
        if not transcript_json.exists():
            raise FileNotFoundError("Transcript JSON not found")
        with transcript_json.open("r", encoding="utf-8") as f:
            data = json.load(f)

        segments = data.get("segments") or []
        if segments:
            srt_text = ASRService.segments_to_srt(segments, data.get("text", ""))
        else:
            text = data.get("text", "")
            duration = get_audio_duration(audio_path)
            srt_text = generate_srt_from_text(text, duration)

        ensure_dir(out_srt.parent)
        with out_srt.open("w", encoding="utf-8") as f:
            f.write(srt_text)
        return out_srt

    @staticmethod
    def write_translated_transcript(base_path: Path, source_data: dict[str, Any], translated_segments: list[dict[str, Any]]) -> tuple[Path, Path]:
        base_path = Path(base_path)
        ensure_dir(base_path.parent)
        json_path = base_path.with_suffix(".vi.transcript.json")
        srt_path = base_path.with_suffix(".vi.transcript.srt")
        text = "\n".join(str(seg.get("text", "")).strip() for seg in translated_segments if str(seg.get("text", "")).strip())
        data = {
            "text": text,
            "segments": translated_segments,
            "source_language": "zh",
            "target_language": "vi",
            "source_text": source_data.get("text", ""),
        }
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with srt_path.open("w", encoding="utf-8") as f:
            f.write(ASRService.segments_to_srt(translated_segments, text))
        return json_path, srt_path
