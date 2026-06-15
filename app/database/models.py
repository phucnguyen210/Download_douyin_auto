from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class VideoRecord:
    source_platform: str
    source_video_id: str
    source_video_url: str
    title: str
    description: str | None = None
    publish_time: int | None = None
    selected_month: str | None = None
    local_video_path: str | None = None
    thumbnail_path: str | None = None
    duration: int | None = None
    file_size: int | None = None
    download_status: str = "pending"
    audio_extract_status: str = "pending"
    background_audio_status: str = "pending"
    asr_status: str = "pending"
    translation_status: str = "pending"
    tts_status: str = "pending"
    audio_merge_status: str = "pending"
    video_merge_status: str = "pending"
    original_audio_path: str | None = None
    no_vocals_audio_path: str | None = None
    transcript_json_path: str | None = None
    transcript_srt_path: str | None = None
    translated_json_path: str | None = None
    translated_srt_path: str | None = None
    tts_segments_directory: str | None = None
    merged_voice_path: str | None = None
    final_audio_path: str | None = None
    final_video_path: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_platform": self.source_platform,
            "source_video_id": self.source_video_id,
            "source_video_url": self.source_video_url,
            "title": self.title,
            "description": self.description,
            "publish_time": self.publish_time,
            "selected_month": self.selected_month,
            "local_video_path": self.local_video_path,
            "thumbnail_path": self.thumbnail_path,
            "duration": self.duration,
            "file_size": self.file_size,
            "download_status": self.download_status,
            "audio_extract_status": self.audio_extract_status,
            "background_audio_status": self.background_audio_status,
            "asr_status": self.asr_status,
            "translation_status": self.translation_status,
            "tts_status": self.tts_status,
            "audio_merge_status": self.audio_merge_status,
            "video_merge_status": self.video_merge_status,
            "original_audio_path": self.original_audio_path,
            "no_vocals_audio_path": self.no_vocals_audio_path,
            "transcript_json_path": self.transcript_json_path,
            "transcript_srt_path": self.transcript_srt_path,
            "translated_json_path": self.translated_json_path,
            "translated_srt_path": self.translated_srt_path,
            "tts_segments_directory": self.tts_segments_directory,
            "merged_voice_path": self.merged_voice_path,
            "final_audio_path": self.final_audio_path,
            "final_video_path": self.final_video_path,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
