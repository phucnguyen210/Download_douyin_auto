from __future__ import annotations

from typing import Any

from app.utils import sort_by_create_time


def sort_old_to_new(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sort_by_create_time(videos)
