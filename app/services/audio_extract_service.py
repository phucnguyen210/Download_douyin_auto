from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.utils.ffmpeg_utils import run_ffmpeg_command, resolve_ffmpeg_path, validate_audio_file
from app.utils import ensure_dir


class AudioExtractService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ffmpeg = resolve_ffmpeg_path(settings.ffmpeg_path)

    def extract_audio(self, video_path: Path, output_dir: Path) -> Path:
        ensure_dir(output_dir)
        output_path = output_dir / "original_audio.wav"

        if validate_audio_file(output_path):
            return output_path

        command = [
            self.ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output_path),
        ]

        run_ffmpeg_command(command)

        if not validate_audio_file(output_path):
            raise RuntimeError(f"Audio extraction created invalid file: {output_path}")

        return output_path

    def check_ffmpeg(self) -> bool:
        try:
            run_ffmpeg_command([self.ffmpeg, "-version"], timeout=10)
            return True
        except Exception:
            return False
