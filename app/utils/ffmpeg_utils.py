from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Sequence


class FfmpegError(Exception):
    pass


def resolve_ffmpeg_path(ffmpeg_path: Path | None = None) -> str:
    if ffmpeg_path:
        return str(ffmpeg_path)
    return "ffmpeg"


def run_ffmpeg_command(command: Sequence[str], timeout: int = 120) -> None:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    if process.returncode != 0:
        raise FfmpegError(
            f"FFmpeg failed: returncode={process.returncode} \n"
            f"command={' '.join(shlex.quote(str(c)) for c in command)}\n"
            f"stderr={process.stderr.strip()}"
        )


def validate_audio_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0
