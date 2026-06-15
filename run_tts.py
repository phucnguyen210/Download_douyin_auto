from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import load_settings, Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.logger import setup_logger
from app.services.tts_service import TTSService
from app.utils import ensure_dir


async def main() -> None:
    settings: Settings = load_settings()
    logger = setup_logger("run_tts")
    db = Database(settings.database_path)
    repo = VideoRepository(db)
    tts = TTSService(settings, logger=logger)

    pending = repo.list_pending_tts()
    if not pending:
        logger.info("No pending TTS jobs found.")
        return

    for row in pending:
        vid = row["id"]
        transcript_json = row.get("translated_json_path") or row.get("transcript_json_path")
        if not transcript_json:
            logger.warning(f"Video {vid} has no transcript_json_path, skipping")
            repo.update_video(vid, {"tts_status": "failed", "error_message": "no transcript"})
            continue
        transcript_json = Path(transcript_json)
        out_dir = Path(settings.output_dir) / "tts"
        ensure_dir(out_dir)
        out_path = out_dir / f"video_{vid}_tts.wav"
        try:
            logger.info(f"Synthesizing TTS for video {vid}")
            result_path = tts.synthesize_from_transcript_file(transcript_json, out_path)
            repo.update_video(vid, {"tts_status": "completed", "merged_voice_path": str(result_path)})
            logger.info(f"TTS completed for video {vid}")
        except Exception as exc:
            logger.exception(f"TTS failed for video {vid}: {exc}")
            repo.update_video(vid, {"tts_status": "failed", "error_message": str(exc)})


if __name__ == "__main__":
    asyncio.run(main())

