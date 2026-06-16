from __future__ import annotations

import os
import re
from pathlib import Path

from openai import OpenAI

from app.config import Settings
from app.logger import setup_logger


SRT_TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}")
CLEAN_SPACES_RE = re.compile(r"\s+")

TITLE_FROM_SRT_PROMPT = """
Bạn là biên tập viên tiêu đề cho video reup phim ngắn/drama tiếng Việt trên Facebook.

Nhiệm vụ: đọc transcript phụ đề và viết 1 tiêu đề tiếng Việt hấp dẫn, đúng nội dung, phù hợp để đăng Fanpage.

Quy tắc bắt buộc:
- Chỉ trả về đúng 1 dòng tiêu đề, không giải thích.
- Không thêm tiền tố như "Tiêu đề:".
- Không dùng Markdown, emoji, hashtag.
- Tiêu đề dài tối đa 100 ký tự.
- Viết tự nhiên, dễ hiểu, có điểm gây tò mò.
- Không bịa tình tiết không có trong transcript.
- Không viết toàn bộ bằng chữ hoa.
- Ưu tiên phong cách drama: mẹ chồng nàng dâu, tổng tài, thiếu gia, hào môn, con dâu, trả thù, thân phận, tình cảm gia đình nếu nội dung phù hợp.
- Nếu transcript cổ trang/huyền huyễn thì dùng văn phong cổ trang nhẹ, không quá khó hiểu.
""".strip()


class TitleGeneratorService:
    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("title_generator")
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = os.getenv("OPENAI_TITLE_MODEL", settings.openai_model or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        self.max_input_chars = int(os.getenv("TITLE_FROM_SRT_MAX_CHARS", "8000") or "8000")
        self.max_title_chars = int(os.getenv("TITLE_MAX_CHARS", "100") or "100")

    def generate_from_srt_file(self, srt_path: str | Path) -> str:
        srt_path = Path(srt_path)
        if not srt_path.exists():
            raise FileNotFoundError(f"SRT file not found: {srt_path}")
        transcript = self._srt_to_text(srt_path.read_text(encoding="utf-8", errors="ignore"))
        if not transcript:
            raise RuntimeError(f"SRT has no usable text: {srt_path}")
        return self.generate_from_text(transcript)

    def generate_from_text(self, transcript: str) -> str:
        transcript = self._normalize_text(transcript)
        if not transcript:
            raise RuntimeError("Transcript text is empty")
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is missing; cannot generate title from SRT")

        transcript = transcript[: self.max_input_chars]
        response = self.client.responses.create(
            model=self.model,
            instructions=TITLE_FROM_SRT_PROMPT,
            input=(
                "Hãy viết tiêu đề tiếng Việt cho video dựa trên transcript sau:\n\n"
                f"{transcript}"
            ),
        )
        title = self._clean_title(response.output_text or "")
        if not title:
            raise RuntimeError("OpenAI returned empty title")
        return title

    def _srt_to_text(self, srt_text: str) -> str:
        lines: list[str] = []
        for raw_line in srt_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            if SRT_TIME_RE.search(line):
                continue
            lines.append(line)
        return self._normalize_text(" ".join(lines))

    def _normalize_text(self, value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value or "")
        value = CLEAN_SPACES_RE.sub(" ", value).strip()
        return value

    def _clean_title(self, value: str) -> str:
        title = (value or "").strip().strip('"\'`')
        title = title.replace("Tiêu đề:", "").replace("Tựa đề:", "").strip()
        title = CLEAN_SPACES_RE.sub(" ", title)
        title = title.replace("#", "").strip()
        if len(title) > self.max_title_chars:
            title = title[: self.max_title_chars].rstrip(" ,.;:-")
        return title