from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import load_settings, Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.logger import setup_logger
from app.services.asr_service import ASRService
from app.utils import ensure_dir


async def main() -> None:
    settings: Settings = load_settings()
    logger = setup_logger("run_asr")
    db = Database(settings.database_path)
    repo = VideoRepository(db)
    asr = ASRService(settings, logger=logger)

    pending = repo.list_pending_asr()
    if not pending:
        logger.info("No pending ASR jobs found.")
        return

    for row in pending:
        vid = row["id"]
        audio_path = row.get("original_audio_path")
        if not audio_path:
            logger.warning(f"Video {vid} has no original_audio_path, skipping")
            repo.update_video(vid, {"asr_status": "failed", "error_message": "no audio path"})
            continue
        audio_path = Path(audio_path)
        try:
            logger.info(f"Transcribing {audio_path}")
            result = await asr.transcribe(audio_path)
            text = result.get("text", "")
            # compute transcript base path next to audio file
            base = audio_path.with_suffix("")
            json_path, srt_path = ASRService.write_transcript_files(base, result)
            repo.update_video(vid, {
                "asr_status": "completed",
                "transcript_json_path": str(json_path),
                "transcript_srt_path": str(srt_path),
            })
            logger.info(f"ASR completed for video {vid}")
        except Exception as exc:
            logger.exception(f"ASR failed for video {vid}: {exc}")
            repo.update_video(vid, {"asr_status": "failed", "error_message": str(exc)})


if __name__ == "__main__":
    asyncio.run(main())

