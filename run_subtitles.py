from __future__ import annotations

from pathlib import Path

from app.config import load_settings, Settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.logger import setup_logger
from app.services.subtitle_service import SubtitleService


def main() -> None:
    settings: Settings = load_settings()
    logger = setup_logger("run_subtitles")
    db = Database(settings.database_path)
    repo = VideoRepository(db)

    pending = repo.list_pending_subtitles()
    if not pending:
        logger.info("No pending subtitle jobs found.")
        return

    for row in pending:
        vid = row["id"]
        transcript_json = row.get("transcript_json_path")
        audio_path = row.get("original_audio_path")
        if not transcript_json or not audio_path:
            logger.warning(f"Video {vid} missing transcript or audio, skipping")
            repo.update_video(vid, {"error_message": "missing transcript or audio"})
            continue
        transcript_json = Path(transcript_json)
        audio_path = Path(audio_path)
        out_srt = transcript_json.with_suffix(".transcript.srt")
        try:
            logger.info(f"Generating SRT for video {vid}")
            result = SubtitleService.create_srt_for_transcript(transcript_json, audio_path, out_srt)
            repo.update_video(vid, {"transcript_srt_path": str(result)})
            logger.info(f"SRT generated for video {vid}")
        except Exception as exc:
            logger.exception(f"SRT generation failed for video {vid}: {exc}")
            repo.update_video(vid, {"error_message": str(exc)})


if __name__ == "__main__":
    main()
