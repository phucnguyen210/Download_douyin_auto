from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from app.utils.ffmpeg_utils import resolve_ffmpeg_path


def get_audio_duration(path: Path, ffprobe_path: Optional[Path] = None) -> float:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    ffprobe = str(ffprobe_path) if ffprobe_path else "ffprobe"
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe error: {proc.stderr.strip()}")
        out = proc.stdout.strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0
