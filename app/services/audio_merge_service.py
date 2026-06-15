from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.logger import setup_logger
from app.utils.ffmpeg_utils import run_ffmpeg_command, resolve_ffmpeg_path
from app.utils import ensure_dir


class AudioMergeService:
    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("audio_merge")
        self.ffmpeg = resolve_ffmpeg_path(settings.ffmpeg_path)

    def merge(
        self,
        original_audio: Path,
        merged_voice: Path,
        out_path: Path,
        original_volume: float = 0.05,
        voice_volume: float = 1.0,
    ) -> Path:
        original_audio = Path(original_audio)
        merged_voice = Path(merged_voice)
        out_path = Path(out_path)
        ensure_dir(out_path.parent)

        if not original_audio.exists():
            raise FileNotFoundError(f"Original audio not found: {original_audio}")
        if not merged_voice.exists() or merged_voice.stat().st_size <= 0:
            raise FileNotFoundError(f"Vietnamese TTS audio not found or empty: {merged_voice}")

        original_volume = max(0.0, float(original_volume))
        voice_volume = max(0.0, float(voice_volume))
        self.logger.info(
            f"Mixing audio with original_volume={original_volume:.2f}, "
            f"voice_volume={voice_volume:.2f}: {merged_voice}"
        )

        filter_complex = (
            f"[0:a]volume={original_volume:.4f}[bg];"
            f"[1:a]volume={voice_volume:.4f}[voice];"
            "[bg][voice]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[aout]"
        )
        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(original_audio),
            "-i",
            str(merged_voice),
            "-filter_complex",
            filter_complex,
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ]
        run_ffmpeg_command(cmd, timeout=1800)
        return out_path
