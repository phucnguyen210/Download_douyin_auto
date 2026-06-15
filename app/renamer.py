from __future__ import annotations

from pathlib import Path

from app.utils import build_final_stem, clean_filename


def build_output_path(
    base_dir: Path,
    index: int,
    date_folder: str,
    translated_title: str,
    hashtags: list[str],
    source_suffix: str,
    max_filename_len: int = 180,
) -> Path:
    folder = base_dir / date_folder
    folder.mkdir(parents=True, exist_ok=True)

    suffix = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
    stem = build_final_stem(index=index, translated_title=translated_title, hashtags=hashtags, max_length=max_filename_len)
    stem = clean_filename(stem, max_length=max_filename_len)
    return folder / f"{stem}{suffix}"


def sanitize_for_display(name: str, max_len: int = 120) -> str:
    return clean_filename(name, max_length=max_len)
