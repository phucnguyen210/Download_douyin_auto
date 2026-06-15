from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

INVALID_FILENAME_CHARS = r'<>:"/\\|?*\x00-\x1F'
INVALID_FILENAME_RE = re.compile(f"[{re.escape(INVALID_FILENAME_CHARS)}]")
WHITESPACE_RE = re.compile(r"\s+")
HASHTAG_RE = re.compile(r"#([^\s#]+)")
MULTI_UNDERSCORE_RE = re.compile(r"_+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    if is_dataclass(data):
        data = asdict(data)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return text.strip()


def remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify_vietnamese(text: str, max_length: int = 180) -> str:
    text = normalize_text(text)
    text = remove_diacritics(text)
    text = text.replace("&", " va ")
    text = INVALID_FILENAME_RE.sub(" ", text)
    text = text.replace("#", " ")
    text = text.replace("'", "")
    text = WHITESPACE_RE.sub("_", text)
    text = re.sub(r"[^0-9A-Za-z_]+", "", text)
    text = MULTI_UNDERSCORE_RE.sub("_", text).strip("_")
    return text[:max_length] if len(text) > max_length else text


def clean_filename(name: str, max_length: int = 180) -> str:
    name = normalize_text(name)
    name = INVALID_FILENAME_RE.sub(" ", name)
    name = WHITESPACE_RE.sub("_", name)
    name = MULTI_UNDERSCORE_RE.sub("_", name).strip("._ ")
    if not name:
        name = "file"
    if len(name) > max_length:
        stem, dot, suffix = name.rpartition(".")
        if dot:
            cutoff = max_length - len(suffix) - 1
            name = f"{stem[:cutoff].rstrip('_')}.{suffix}"
        else:
            name = name[:max_length]
    return name


def extract_hashtags(text: str) -> list[str]:
    return [tag for tag in HASHTAG_RE.findall(text or "") if tag]


def split_title_and_hashtags(text: str) -> tuple[str, list[str]]:
    tags = extract_hashtags(text)
    title = HASHTAG_RE.sub("", text or "")
    title = WHITESPACE_RE.sub(" ", title).strip()
    return title, tags


def normalize_hashtag(tag: str) -> str:
    tag = normalize_text(tag).lstrip("#")
    tag = slugify_vietnamese(tag, max_length=40)
    return tag.lower()


def build_final_stem(index: int, translated_title: str, hashtags: Iterable[str], max_length: int = 180) -> str:
    parts = [f"{index:04d}", slugify_vietnamese(translated_title, max_length=max_length)]
    for tag in hashtags:
        safe = normalize_hashtag(tag)
        if safe:
            parts.append(safe)
    stem = "_".join(part for part in parts if part)
    stem = MULTI_UNDERSCORE_RE.sub("_", stem).strip("_")
    return stem[:max_length] if len(stem) > max_length else stem


def extract_date_folder(ts: int | float | None) -> str:
    if not ts:
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def sort_by_create_time(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[int, str]:
        ts = item.get("create_time") or item.get("timestamp") or 0
        aweme_id = str(item.get("aweme_id") or item.get("id") or "")
        try:
            ts_val = int(ts)
        except Exception:
            ts_val = 0
        return (ts_val, aweme_id)

    return sorted(items, key=key)


def safe_video_key(video: dict[str, Any]) -> str:
    return str(video.get("aweme_id") or video.get("id") or video.get("webpage_url") or video.get("url") or "")


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default
