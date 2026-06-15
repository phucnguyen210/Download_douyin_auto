from __future__ import annotations

from pathlib import Path

from app.config import load_settings, Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.logger import setup_logger
from app.services.audio_merge_service import AudioMergeService


def main() -> None:
    settings: Settings = load_settings()
    logger = setup_logger("run_audio_merge")
    db = Database(settings.database_path)
    repo = VideoRepository(db)
    merger = AudioMergeService(settings, logger=logger)

    pending = repo.list_pending_audio_merge()
    if not pending:
        logger.info("No pending audio merge jobs found.")
        return

    for row in pending:
        vid = row["id"]
        orig = row.get("original_audio_path")
        merged = row.get("merged_voice_path")
        if not orig or not merged:
            logger.warning(f"Video {vid} missing audio paths, skipping")
            repo.update_video(vid, {"audio_merge_status": "failed", "error_message": "missing audio paths"})
            continue
        out_dir = Path(settings.output_dir) / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"video_{vid}_final_audio.m4a"
        try:
            logger.info(f"Merging audio for video {vid}")
            result = merger.merge(Path(orig), Path(merged), out_path)
            repo.update_video(vid, {"audio_merge_status": "completed", "final_audio_path": str(result)})
            logger.info(f"Audio merge completed for video {vid}")
        except Exception as exc:
            logger.exception(f"Audio merge failed for video {vid}: {exc}")
            repo.update_video(vid, {"audio_merge_status": "failed", "error_message": str(exc)})


if __name__ == "__main__":
    main()
