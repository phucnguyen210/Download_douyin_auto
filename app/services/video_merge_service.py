from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.logger import setup_logger
from app.utils.ffmpeg_utils import run_ffmpeg_command, resolve_ffmpeg_path
from app.utils import ensure_dir


class VideoMergeService:
    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("video_merge")
        self.ffmpeg = resolve_ffmpeg_path(settings.ffmpeg_path)

    def mux_audio_into_video(self, video_path: Path, audio_path: Path, out_path: Path) -> Path:
        """Mux processed audio and export a Facebook-friendly H.264/AAC MP4.

        Douyin downloads are often HEVC/H.265. Copying the video stream keeps that
        codec, which can cause black video or failed previews on Facebook/Windows.
        Re-encoding here makes the final render compatible with common players.
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        out_path = Path(out_path)
        ensure_dir(out_path.parent)

        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(out_path),
        ]
        self.logger.info("Exporting final video as H.264/AAC: %s", out_path)
        run_ffmpeg_command(cmd, timeout=7200)
        return out_path

    def transcode_to_h264(self, video_path: Path, out_path: Path) -> Path:
        """Convert an existing downloaded video to H.264/AAC without changing content."""
        video_path = Path(video_path)
        out_path = Path(out_path)
        ensure_dir(out_path.parent)
        cmd = [
            self.ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        self.logger.info("Transcoding video as H.264/AAC: %s", out_path)
        run_ffmpeg_command(cmd, timeout=7200)
        return out_path