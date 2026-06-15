from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.db import Database


class VideoRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_video(self, video_data: dict[str, Any]) -> int:
        now = datetime.now().isoformat()
        params = {
            "source_platform": video_data.get("source_platform", "douyin"),
            "source_video_id": video_data.get("source_video_id", ""),
            "source_video_url": video_data.get("source_video_url", ""),
            "title": video_data.get("title", ""),
            "description": video_data.get("description"),
            "publish_time": video_data.get("publish_time"),
            "selected_month": video_data.get("selected_month"),
            "local_video_path": video_data.get("local_video_path"),
            "thumbnail_path": video_data.get("thumbnail_path"),
            "duration": video_data.get("duration"),
            "file_size": video_data.get("file_size"),
            "download_status": video_data.get("download_status", "pending"),
            "audio_extract_status": video_data.get("audio_extract_status", "pending"),
            "background_audio_status": video_data.get("background_audio_status", "pending"),
            "asr_status": video_data.get("asr_status", "pending"),
            "translation_status": video_data.get("translation_status", "pending"),
            "tts_status": video_data.get("tts_status", "pending"),
            "audio_merge_status": video_data.get("audio_merge_status", "pending"),
            "video_merge_status": video_data.get("video_merge_status", "pending"),
            "original_audio_path": video_data.get("original_audio_path"),
            "no_vocals_audio_path": video_data.get("no_vocals_audio_path"),
            "transcript_json_path": video_data.get("transcript_json_path"),
            "transcript_srt_path": video_data.get("transcript_srt_path"),
            "translated_json_path": video_data.get("translated_json_path"),
            "translated_srt_path": video_data.get("translated_srt_path"),
            "tts_segments_directory": video_data.get("tts_segments_directory"),
            "merged_voice_path": video_data.get("merged_voice_path"),
            "final_audio_path": video_data.get("final_audio_path"),
            "final_video_path": video_data.get("final_video_path"),
            "error_message": video_data.get("error_message"),
            "created_at": now,
            "updated_at": now,
        }
        query = """
            INSERT OR IGNORE INTO videos (
                source_platform,
                source_video_id,
                source_video_url,
                title,
                description,
                publish_time,
                selected_month,
                local_video_path,
                thumbnail_path,
                duration,
                file_size,
                download_status,
                audio_extract_status,
                background_audio_status,
                asr_status,
                translation_status,
                tts_status,
                audio_merge_status,
                video_merge_status,
                original_audio_path,
                no_vocals_audio_path,
                transcript_json_path,
                transcript_srt_path,
                translated_json_path,
                translated_srt_path,
                tts_segments_directory,
                merged_voice_path,
                final_audio_path,
                final_video_path,
                error_message,
                created_at,
                updated_at
            ) VALUES (
                :source_platform,
                :source_video_id,
                :source_video_url,
                :title,
                :description,
                :publish_time,
                :selected_month,
                :local_video_path,
                :thumbnail_path,
                :duration,
                :file_size,
                :download_status,
                :audio_extract_status,
                :background_audio_status,
                :asr_status,
                :translation_status,
                :tts_status,
                :audio_merge_status,
                :video_merge_status,
                :original_audio_path,
                :no_vocals_audio_path,
                :transcript_json_path,
                :transcript_srt_path,
                :translated_json_path,
                :translated_srt_path,
                :tts_segments_directory,
                :merged_voice_path,
                :final_audio_path,
                :final_video_path,
                :error_message,
                :created_at,
                :updated_at
            )
        """
        cursor = self.db.execute(query, params)
        self.db.connection.commit()
        return cursor.lastrowid

    def update_video(self, video_id: int, update_data: dict[str, Any]) -> None:
        if not update_data:
            return
        now = datetime.now().isoformat()
        update_data = update_data.copy()
        update_data["updated_at"] = now
        set_clause = ", ".join(f"{key} = :{key}" for key in update_data.keys())
        query = f"UPDATE videos SET {set_clause} WHERE id = :id"
        update_data["id"] = video_id
        self.db.execute(query, update_data)
        self.db.connection.commit()

    def get_video_by_source_id(self, source_video_id: str) -> dict[str, Any] | None:
        query = "SELECT * FROM videos WHERE source_video_id = ?"
        row = self.db.execute(query, (source_video_id,)).fetchone()
        return dict(row) if row else None

    def get_video_by_url(self, source_video_url: str) -> dict[str, Any] | None:
        query = "SELECT * FROM videos WHERE source_video_url = ?"
        row = self.db.execute(query, (source_video_url,)).fetchone()
        return dict(row) if row else None

    def upsert_video(self, video_data: dict[str, Any]) -> int:
        existing = self.get_video_by_source_id(video_data.get("source_video_id", ""))
        if existing:
            self.update_video(existing["id"], video_data)
            return existing["id"]
        existing = self.get_video_by_url(video_data.get("source_video_url", ""))
        if existing:
            self.update_video(existing["id"], video_data)
            return existing["id"]
        return self.create_video(video_data)

    def list_videos(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        query = "SELECT * FROM videos ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = self.db.execute(query, (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def list_pending_downloads(self) -> list[dict[str, Any]]:
        query = "SELECT * FROM videos WHERE download_status IN ('pending', 'failed') ORDER BY created_at DESC"
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_audio_extractions(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE download_status = 'completed' "
            "AND audio_extract_status IN ('pending', 'failed') "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_asr(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE audio_extract_status = 'completed' "
            "AND asr_status IN ('pending', 'failed') "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_tts(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE asr_status = 'completed' "
            "AND tts_status IN ('pending', 'failed') "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_audio_merge(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE tts_status = 'completed' "
            "AND audio_merge_status IN ('pending', 'failed') "
            "AND original_audio_path IS NOT NULL "
            "AND merged_voice_path IS NOT NULL "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_video_merge(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE audio_merge_status = 'completed' "
            "AND video_merge_status IN ('pending', 'failed') "
            "AND final_audio_path IS NOT NULL "
            "AND local_video_path IS NOT NULL "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_pending_subtitles(self) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM videos "
            "WHERE asr_status = 'completed' "
            "AND transcript_json_path IS NOT NULL "
            "AND (transcript_srt_path IS NULL OR transcript_srt_path = '') "
            "ORDER BY created_at DESC"
        )
        rows = self.db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def list_completed_videos(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        query = "SELECT * FROM videos WHERE download_status = 'completed' ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = self.db.execute(query, (limit, offset)).fetchall()
        return [dict(row) for row in rows]
