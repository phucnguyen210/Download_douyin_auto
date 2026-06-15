from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


console = Console()


def setup_logger(name: str = "douyin_downloader", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_level=True,
        show_path=False,
    )
    handler.setLevel(level)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Optional plain file log for post-mortem debugging.
    from pathlib import Path

    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(logs_dir / "app.log"), encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(file_handler)
    return logger


@dataclass(slots=True)
class ProgressState:
    last_percent: float = -1.0
    last_speed: str = ""
    last_eta: str = ""


def render_kv(**kwargs: Any) -> str:
    parts: list[str] = []
    for key, value in kwargs.items():
        parts.append(f"[bold cyan]{key}[/bold cyan]=[white]{value}[/white]")
    return " | ".join(parts)
