from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

douyin_cookie: str = os.getenv("DOUYIN_COOKIE", "")
cookie_file: Path = Path("cookies.txt")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_path(name: str, default: str) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value) if value else Path(default)


@dataclass(slots=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    openai_asr_model: str = os.getenv("OPENAI_ASR_MODEL", "whisper-1").strip()
    cookie_file: Path | None = (
        Path(os.getenv("DOUYIN_COOKIE_FILE").strip())
        if os.getenv("DOUYIN_COOKIE_FILE", "").strip()
        else None
    )
    cookies_from_browser: str | None = (
        os.getenv("DOUYIN_COOKIES_FROM_BROWSER", "").strip() or None
    )
    downloads_dir: Path = _env_path("DOWNLOADS_DIR", "downloads")
    output_dir: Path = _env_path("OUTPUT_DIR", "output")
    database_path: Path = _env_path("DATABASE_PATH", "data/app.db")
    ffmpeg_path: Path | None = (
        Path(os.getenv("FFMPEG_PATH").strip())
        if os.getenv("FFMPEG_PATH", "").strip()
        else None
    )
    ffprobe_path: Path | None = (
        Path(os.getenv("FFPROBE_PATH").strip())
        if os.getenv("FFPROBE_PATH", "").strip()
        else None
    )
    logs_dir: Path = _env_path("LOGS_DIR", "logs")
    state_file: Path = _env_path("STATE_FILE", "download_state.json")
    metadata_file: Path = _env_path("METADATA_FILE", "metadata.json")
    max_retries: int = _env_int("MAX_RETRIES", 5)
    download_concurrency: int = _env_int("DOWNLOAD_CONCURRENCY", 1)
    translation_concurrency: int = _env_int("TRANSLATION_CONCURRENCY", 4)
    max_filename_len: int = _env_int("MAX_FILENAME_LEN", 180)
    socket_timeout: int = _env_int("SOCKET_TIMEOUT", 30)
    concurrent_fragments: int = _env_int("CONCURRENT_FRAGMENTS", 4)
    dedupe_by_hash: bool = os.getenv("DEDUPE_BY_HASH", "0").strip() == "1"


def load_settings() -> Settings:
    settings = Settings()
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
