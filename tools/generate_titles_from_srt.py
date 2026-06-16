from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.database.db import Database
from app.services.title_service import TitleGeneratorService


def _resolve(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path


def _pick_srt(row: dict) -> Path | None:
    for key in ("translated_srt_path", "transcript_srt_path"):
        path = _resolve(row.get(key))
        if path and path.exists():
            return path
    final_video = _resolve(row.get("final_video_path"))
    if final_video:
        candidates = [
            final_video.with_suffix(".final.srt"),
            final_video.with_suffix(".srt"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Facebook titles from SRT files and save to Douyin SQLite DB.")
    parser.add_argument("--db", default="", help="Default: DATABASE_PATH from .env or data/app.db")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even when title already looks custom.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    db_path = Path(args.db) if args.db else settings.database_path
    db = Database(db_path)
    title_service = TitleGeneratorService(settings)

    rows = db.execute(
        """
        SELECT * FROM videos
        WHERE COALESCE(final_video_path, '') != ''
          AND COALESCE(video_merge_status, '') = 'completed'
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()

    updated = 0
    skipped = 0
    failed = 0
    for row in rows:
        item = dict(row)
        current_title = str(item.get("title") or "").strip()
        source_id = str(item.get("source_video_id") or "").strip()
        if current_title and current_title != source_id and not args.overwrite:
            skipped += 1
            print(f"SKIP id={item['id']}: title already set: {current_title}")
            continue

        srt_path = _pick_srt(item)
        if not srt_path:
            skipped += 1
            print(f"SKIP id={item['id']}: no SRT found")
            continue

        try:
            title = title_service.generate_from_srt_file(srt_path)
            print(f"TITLE id={item['id']}: {title}")
            if not args.dry_run:
                db.execute(
                    "UPDATE videos SET title = ?, updated_at = datetime('now') WHERE id = ?",
                    (title, item["id"]),
                )
                db.connection.commit()
            updated += 1
        except Exception as exc:
            failed += 1
            print(f"FAILED id={item['id']}: {exc}")

    db.close()
    print(f"Done. updated={updated}, skipped={skipped}, failed={failed}, dry_run={args.dry_run}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())