from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime
if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional
import shutil

from app.config import load_settings
from app.database.db import Database
from app.database.repositories import VideoRepository
from app.douyin import DouyinDownloader, VideoMeta
from app.logger import setup_logger
from app.sorter import sort_old_to_new
from app.translator import Translator
from app.utils import (
    atomic_write_json,
    ensure_dir,
    extract_date_folder,
    now_iso,
    read_json,
    sha256_file,
)


class StateManager:
    def __init__(self, state_file: Path, metadata_file: Path) -> None:
        self.state_file = state_file
        self.metadata_file = metadata_file
        self.state = read_json(self.state_file, {"videos": {}, "order": [], "profile_url": ""})

    def is_done(self, aweme_id: str) -> bool:
        return self.state.get("videos", {}).get(aweme_id, {}).get("status") == "done"

    def mark_processing(self, video: VideoMeta, index: int) -> None:
        self.state.setdefault("videos", {})
        self.state["videos"][video.aweme_id] = {
            "status": "processing",
            "index": index,
            "aweme_id": video.aweme_id,
            "title": video.title,
            "hashtags": video.hashtags,
            "create_time": video.create_time,
            "video_url": video.video_url,
            "webpage_url": video.webpage_url,
            "updated_at": now_iso(),
        }
        self._flush()

    def mark_done(self, video: VideoMeta, index: int, translated: str, hashtags: list[str], target_path: Path, checksum: str | None = None) -> None:
        self.state.setdefault("videos", {})
        self.state["videos"][video.aweme_id] = {
            "status": "done",
            "index": index,
            "aweme_id": video.aweme_id,
            "title": video.title,
            "translated_title": translated,
            "hashtags": hashtags,
            "create_time": video.create_time,
            "video_url": video.video_url,
            "webpage_url": video.webpage_url,
            "target_path": str(target_path),
            "sha256": checksum,
            "updated_at": now_iso(),
        }
        self._flush()

    def _flush(self) -> None:
        atomic_write_json(self.state_file, self.state)
        atomic_write_json(self.metadata_file, self.state)

    def completed_count(self) -> int:
        return sum(1 for v in self.state.get("videos", {}).values() if v.get("status") == "done")


async def process_one(
    idx: int,
    video: VideoMeta,
    downloader: DouyinDownloader,
    translator: Translator,
    settings,
    state: StateManager,
    repository: VideoRepository,
    logger,
    selected_month: str | None = None,
) -> None:
    existing_record = repository.get_video_by_source_id(video.aweme_id)
    if not existing_record:
        existing_record = repository.get_video_by_url(video.video_url)

    if existing_record and existing_record.get("download_status") == "completed":
        logger.info(f"[dim]Bỏ qua[/dim] {video.aweme_id} vì đã tải trước đó")
        return

    logger.info(
        f"Xử lý #{idx:04d} | aweme_id={video.aweme_id} | create_time={video.create_time} | title={video.title}"
    )

    video_data = {
        "source_platform": "douyin",
        "source_video_id": video.aweme_id,
        "source_video_url": video.video_url,
        "title": video.title,
        "publish_time": video.create_time,
        "selected_month": selected_month,
        "download_status": "processing",
    }

    if existing_record:
        repository.update_video(existing_record["id"], video_data)
        video_id = existing_record["id"]
    else:
        video_id = repository.create_video(video_data)

    state.mark_processing(video, idx)

    try:
        translated = await translator.translate(video.title)
        logger.info(f"[green]Đã dịch[/green] {video.aweme_id}: {translated.translated_title}")

        run_date = datetime.now().strftime("%Y-%m-%d")
        batch_no = (idx - 1) // 10 + 1
        target_dir = settings.downloads_dir / run_date / f"batch_{batch_no:03d}"

        final_path = await downloader.download_video(
            video=video,
            target_dir=target_dir,
            index=idx,
            translated_title=translated.translated_title,
            hashtags=translated.hashtags,
        )

        file_size = final_path.stat().st_size if final_path.exists() else None
        checksum = await asyncio.to_thread(sha256_file, final_path)

        update_data = {
            "local_video_path": str(final_path),
            "file_size": file_size,
            "download_status": "completed",
            "error_message": None,
        }
        repository.update_video(video_id, update_data)

        state.mark_done(
            video=video,
            index=idx,
            translated=translated.translated_title,
            hashtags=translated.hashtags,
            target_path=final_path,
            checksum=checksum,
        )
        logger.info(f"[bold green]Hoàn tất[/bold green] -> {final_path}")

    except Exception as exc:
        logger.exception(f"Lỗi download {video.aweme_id}: {type(exc).__name__}: {exc}")
        repository.update_video(video_id, {
            "download_status": "failed",
            "error_message": str(exc),
        })
        raise


async def amain(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Douyin downloader + translator")
    parser.add_argument(
        "profile_url"
    )

    parser.add_argument(
        "target_month",
        nargs="?",
        default=None,
        help="YYYY-MM"
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of videos")
    args = parser.parse_args(argv)

    settings = load_settings()
    logger = setup_logger("main")
    state = StateManager(settings.state_file, settings.metadata_file)
    db = Database(settings.database_path)
    repository = VideoRepository(db)
    downloader = DouyinDownloader(settings, logger=logger)
    translator = Translator(settings, logger=logger)

    if not settings.openai_api_key:
        logger.error("Thiếu OPENAI_API_KEY trong .env")
        return 2

    videos = await downloader.crawl_profile(args.profile_url,args.target_month)
    videos = sort_old_to_new([v.to_dict() for v in videos])
    if args.limit and args.limit > 0:
        videos = videos[: args.limit]

    logger.info(f"Bắt đầu xử lý {len(videos)} video, old -> new")
    state.state["profile_url"] = args.profile_url
    state.state["order"] = [v.get("aweme_id") for v in videos]
    state._flush()

    for idx, item in enumerate(videos, start=1):
        video = VideoMeta(
            aweme_id=str(item["aweme_id"]),
            title=str(item["title"]),
            hashtags=list(item.get("hashtags") or []),
            create_time=int(item.get("create_time") or 0),
            video_url=str(item.get("video_url") or ""),
            webpage_url=str(item.get("webpage_url") or ""),
            raw=dict(item.get("raw") or {}),
        )
        try:
            await process_one(
                idx,
                video,
                downloader,
                translator,
                settings,
                state,
                repository,
                logger,
                args.target_month,
            )
        except Exception as exc:
            logger.exception(f"Lỗi với {video.aweme_id}: {type(exc).__name__}: {exc}")
            continue

    logger.info(
        f"Xong. Đã hoàn tất {state.completed_count()}/{len(videos)} video"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
