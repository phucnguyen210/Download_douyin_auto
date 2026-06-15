from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.connection = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_platform TEXT NOT NULL,
                    source_video_id TEXT NOT NULL,
                    source_video_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    publish_time INTEGER,
                    selected_month TEXT,
                    local_video_path TEXT,
                    thumbnail_path TEXT,
                    duration INTEGER,
                    file_size INTEGER,
                    download_status TEXT NOT NULL DEFAULT 'pending',
                    audio_extract_status TEXT NOT NULL DEFAULT 'pending',
                    background_audio_status TEXT NOT NULL DEFAULT 'pending',
                    asr_status TEXT NOT NULL DEFAULT 'pending',
                    translation_status TEXT NOT NULL DEFAULT 'pending',
                    tts_status TEXT NOT NULL DEFAULT 'pending',
                    audio_merge_status TEXT NOT NULL DEFAULT 'pending',
                    video_merge_status TEXT NOT NULL DEFAULT 'pending',
                    original_audio_path TEXT,
                    no_vocals_audio_path TEXT,
                    transcript_json_path TEXT,
                    transcript_srt_path TEXT,
                    translated_json_path TEXT,
                    translated_srt_path TEXT,
                    tts_segments_directory TEXT,
                    merged_voice_path TEXT,
                    final_audio_path TEXT,
                    final_video_path TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_video_id),
                    UNIQUE(source_video_url)
                )
                """
            )

    def execute(self, query: str, params: tuple | dict | None = None) -> sqlite3.Cursor:
        cur = self.connection.cursor()
        if params is None:
            cur.execute(query)
        else:
            cur.execute(query, params)
        return cur

    def executemany(self, query: str, seq_of_params: list[tuple]) -> sqlite3.Cursor:
        cur = self.connection.cursor()
        cur.executemany(query, seq_of_params)
        return cur

    def query(self, query: str, params: tuple | dict | None = None) -> Iterator[sqlite3.Row]:
        cur = self.execute(query, params)
        return cur.fetchall()

    def close(self) -> None:
        self.connection.close()
