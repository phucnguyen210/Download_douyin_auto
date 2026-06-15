from __future__ import annotations

from pathlib import Path

from app.config import load_settings, Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.logger import setup_logger
from app.services.video_merge_service import VideoMergeService


def main() -> None:
    settings: Settings = load_settings()
    logger = setup_logger("run_video_merge")
    db = Database(settings.database_path)
    repo = VideoRepository(db)
    merger = VideoMergeService(settings, logger=logger)

    pending = repo.list_pending_video_merge()
    if not pending:
        logger.info("No pending video merge jobs found.")
        return

    for row in pending:
        vid = row["id"]
        final_audio = row.get("final_audio_path")
        video_path = row.get("local_video_path")
        if not final_audio or not video_path:
            logger.warning(f"Video {vid} missing final_audio or video path, skipping")
            repo.update_video(vid, {"video_merge_status": "failed", "error_message": "missing paths"})
            continue
        out_dir = Path(settings.output_dir) / "video"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"video_{vid}_final.mp4"
        try:
            logger.info(f"Merging audio into video for {vid}")
            result = merger.mux_audio_into_video(Path(video_path), Path(final_audio), out_path)
            repo.update_video(vid, {"video_merge_status": "completed", "final_video_path": str(result)})
            logger.info(f"Video merge completed for video {vid}")
        except Exception as exc:
            logger.exception(f"Video merge failed for video {vid}: {exc}")
            repo.update_video(vid, {"video_merge_status": "failed", "error_message": str(exc)})


if __name__ == "__main__":
    main()
