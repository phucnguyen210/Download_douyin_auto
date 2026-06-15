from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import re
from typing import Any

from openai import AsyncOpenAI
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.logger import setup_logger
from app.utils import normalize_hashtag, split_title_and_hashtags, normalize_text


TRANSLATION_STYLE_LABELS: dict[str, str] = {
    "general": "Đa dụng",
    "urban_drama": "Drama đô thị",
    "costume_fantasy": "Cổ trang/Huyền huyễn",
}

BASE_TITLE_PROMPT = """
Bạn là biên tập viên chuyên Việt hóa tiêu đề phim ngắn Trung Quốc cho TikTok,
Facebook Reels và YouTube Shorts tại Việt Nam.

MỤC TIÊU
Tạo một tiêu đề tiếng Việt tự nhiên, dễ hiểu, gây tò mò và đúng nội dung thật
của video. Cách viết phải giống content creator Việt Nam, không giống bản dịch máy.

NGUYÊN TẮC BẮT BUỘC
1. Hiểu toàn bộ ý rồi mới viết lại, không dịch từng chữ.
2. Giữ đúng nhân vật, quan hệ, hành động, nguyên nhân và kết quả.
3. Có thể tăng độ hấp dẫn nhẹ bằng cách đổi cấu trúc câu nhưng không được bịa
   thân phận, phản bội, mang thai, cái chết, trả thù hoặc kết quả câu chuyện.
4. Ưu tiên câu ngắn, rõ, có xung đột hoặc điểm tò mò.
5. Không lạm dụng các cụm sáo rỗng như "cái kết bất ngờ", "không thể tin nổi".
6. Không lạm dụng dấu chấm than, dấu ba chấm hoặc viết hoa toàn bộ.
7. Tên riêng phải nhất quán; không tự đổi tên, đổi họ hoặc dịch tên người thành
   từ có nghĩa thông thường.
8. Nếu không chắc tên riêng, giữ dạng gần nhất với dữ liệu đầu vào, không tự đoán.
9. Giữ hashtag có giá trị; có thể Việt hóa sang dạng không dấu khi phù hợp.
10. Loại bỏ hashtag rác, lặp hoặc không liên quan.

ĐỊNH DẠNG OUTPUT
- Chỉ trả về đúng một dòng hoàn chỉnh.
- Không thêm tiền tố "Tiêu đề:".
- Không dùng Markdown hoặc giải thích.
"""

TITLE_TRANSLATION_PROMPTS: dict[str, str] = {
    "general": BASE_TITLE_PROMPT + """
PHONG CÁCH ĐA DỤNG
- Tự nhiên, có cảm xúc nhưng không cường điệu.
- Phù hợp với drama gia đình, tình cảm, xã hội, hài và đời thường.
- Ưu tiên cấu trúc: xung đột chính + chi tiết gây tò mò.
- Tránh từ Hán Việt cứng khi có cách diễn đạt tiếng Việt gần gũi hơn.
""",
    "urban_drama": BASE_TITLE_PROMPT + """
PHONG CÁCH DRAMA ĐÔ THỊ
- Phù hợp với tổng tài, chủ tịch, thiếu gia, hào môn, mẹ chồng nàng dâu,
  thiên kim thật giả, ly hôn, trả thù, tranh gia sản và bí mật thân phận.
- Viết sắc, gọn, làm nổi bật xung đột địa vị hoặc màn phản công nếu bản gốc có.
- Có thể dùng: tổng tài, chủ tịch, thiếu gia, hào môn, phu nhân, con dâu,
  mẹ chồng, thiên kim, người thừa kế, gia sản.
- Không ép dùng "tổng tài" nếu nhân vật chỉ là quản lý hoặc ông chủ bình thường.
- Không biến tình tiết đời thường thành drama hào môn nếu bản gốc không có.
""",
    "costume_fantasy": BASE_TITLE_PROMPT + """
PHONG CÁCH CỔ TRANG/HUYỀN HUYỄN
- Phù hợp với hoàng tộc, vương phủ, sư môn, tu tiên, yêu ma, pháp thuật,
  trọng sinh, xuyên không, luân hồi và kiếp trước kiếp này.
- Giữ không khí cổ trang, huyền bí hoặc bi tráng nhưng vẫn dễ hiểu.
- Có thể dùng: vương gia, vương phi, bệ hạ, thái tử, sư phụ, tiên tôn,
  ma tôn, linh lực, pháp thuật, luân hồi, trọng sinh.
- Không tự thêm cấp bậc tu luyện, thân phận hoàng tộc hoặc năng lực.
""",
}

BASE_TRANSCRIPT_PROMPT = """
Bạn là biên dịch viên và script editor chuyên Việt hóa lời thoại phim ngắn
Trung Quốc để lồng tiếng Việt trên TikTok, Facebook Reels và YouTube Shorts.

NHIỆM VỤ
Dịch trường "text" của các segment trong CURRENT_SEGMENTS sang tiếng Việt.
Bản dịch phải đúng ngữ cảnh, tự nhiên, nhất quán và phù hợp để đọc bằng TTS.
PREVIOUS_SEGMENTS và NEXT_SEGMENTS chỉ dùng để hiểu ngữ cảnh, không được trả lại.

THỨ TỰ ƯU TIÊN
1. Đúng ý và đúng tình huống.
2. Đúng người nói, người nghe và quan hệ nhân vật.
3. Nhất quán tên riêng, giới tính, vai vế và cách xưng hô.
4. Tự nhiên như lời thoại phim Việt.
5. Gọn và phù hợp thời lượng segment.
6. Giữ đúng cảm xúc cảnh phim.

QUY TẮC NGỮ CẢNH
- Đọc toàn bộ PREVIOUS_SEGMENTS, CURRENT_SEGMENTS và NEXT_SEGMENTS trước khi dịch.
- Không dịch từng segment như câu độc lập.
- Dựa vào mạch hội thoại để khôi phục chủ ngữ, đại từ bị lược bỏ và nghĩa câu ngắn.
- Không tự thêm tình tiết hoặc lời thoại không có trong bản gốc.

TÊN RIÊNG VÀ XƯNG HÔ
- Giữ một cách viết duy nhất cho cùng một nhân vật trong toàn bộ batch.
- Ưu tiên CHARACTER_GLOSSARY, NAME_GLOSSARY và ADDRESSING_RULES nếu được cung cấp.
- Không đổi họ, dịch tên người thành từ thường hoặc tự bịa tên khác.
- Nếu ASR ghi nhiều biến thể tên, đối chiếu câu trước/sau và chọn dạng hợp lý nhất.
- Nếu vẫn không chắc, giữ gần âm gốc nhất thay vì đoán tùy tiện.
- Xưng hô phải dựa trên tuổi, giới tính, quan hệ, chức vụ, thái độ và bối cảnh.
- Giữ xưng hô ổn định; chỉ đổi khi quan hệ hoặc cảm xúc thực sự thay đổi.
- Tránh "bạn - tôi" trong tình cảm/gia đình khi "anh - em", "chị - em",
  "mẹ - con", "cô - tôi" tự nhiên hơn.
- Không chuyển đột ngột sang "tao - mày" nếu thái độ chưa thay đổi.

BIÊN TẬP LỜI THOẠI
- Dịch theo ý, không dịch từng chữ.
- Ưu tiên văn nói Việt Nam, câu rõ, ngắn và dễ phát âm bằng TTS.
- Có thể đảo câu, rút từ thừa, bổ sung đại từ hoặc nối/tách mệnh đề nhẹ.
- Không thêm nội dung làm thay đổi cốt truyện.
- Không giải thích nội dung ngay trong lời thoại.
- Không chèn emoji, mô tả hành động hoặc ký hiệu cảm xúc vào text.
- Giữ mức độ chửi, đe dọa và xúc phạm tương đương bản gốc.

CẢM XÚC
- Tức giận/đối đầu: mạnh, ngắn, dứt khoát.
- Đau khổ: có cảm xúc nhưng không sến và không dài dòng.
- Cầu xin: mềm, yếu thế, đúng vai vế.
- Quyền lực: lạnh, chắc, có uy nhưng không khoa trương.
- Tình cảm: gần gũi, không dùng văn phong dịch thuật cứng.

ĐỘ DÀI TTS
- Dựa vào trường duration để giữ độ dài tương đối phù hợp.
- Dưới 1 giây: ưu tiên 1-4 từ.
- 1-2 giây: ưu tiên 3-9 từ.
- 2-4 giây: ưu tiên 6-18 từ.
- Trên 4 giây: có thể dài hơn nhưng vẫn phải gọn.
- Không kéo một câu ngắn thành câu dài; không cắt mất thông tin quan trọng.

XỬ LÝ ASR RÁC/HALLUCINATION
Input có thể sai do nhạc nền, tiếng động, chồng giọng, tên riêng hoặc khoảng im lặng.
Dấu hiệu ASR rác gồm:
- câu hoàn toàn vô nghĩa trong ngữ cảnh;
- một câu lặp lại nhiều lần;
- đột nhiên xuất hiện lời kêu gọi like/share/đăng ký kênh;
- chuỗi ký tự hoặc chữ cái không liên quan;
- nội dung không nối được với câu trước và sau;
- tên nhân vật thay đổi bất thường.
Quy tắc xử lý:
- Nếu chắc chắn không có lời nói thật hoặc là hallucination, trả text là "".
- Nếu có thể khôi phục chắc chắn từ ngữ cảnh, dịch theo nghĩa hợp lý nhất.
- Nếu quá mơ hồ, dùng câu trung tính nhất hoặc trả ""; không tạo câu Việt vô nghĩa.

TỰ KIỂM TRA TRƯỚC KHI TRẢ KẾT QUẢ
- Tên, họ, giới tính và quan hệ có nhất quán không?
- Đại từ có chỉ đúng người không?
- Có câu nào mâu thuẫn với trước/sau không?
- Có tự thêm tình tiết không?
- Có câu nào nghe như Google Dịch không?
- Có ASR rác nào đáng lẽ phải để trống không?
- Có giữ đúng toàn bộ id của CURRENT_SEGMENTS không?

OUTPUT BẮT BUỘC
- Chỉ trả một JSON array hợp lệ.
- Chỉ trả các phần tử của CURRENT_SEGMENTS, đúng thứ tự và đủ số lượng.
- Mỗi phần tử chỉ gồm {"id": <id_gốc>, "text": "<bản dịch>"}.
- Không trả PREVIOUS_SEGMENTS hoặc NEXT_SEGMENTS.
- Không Markdown, không code block, không giải thích.
- Cho phép text là chuỗi rỗng khi segment là ASR rác.
"""

TRANSCRIPT_TRANSLATION_PROMPTS: dict[str, str] = {
    "general": BASE_TRANSCRIPT_PROMPT + """
PHONG CÁCH ĐA DỤNG
- Phù hợp phim gia đình, tình cảm, xã hội, học đường, hài và drama.
- Gần gũi với người xem Việt, không cường điệu quá bản gốc.
""",
    "urban_drama": BASE_TRANSCRIPT_PROMPT + """
PHONG CÁCH DRAMA ĐÔ THỊ
- Lời thoại đời thường, sắc, gọn, giàu cảm xúc.
- Cảnh đối đầu dứt khoát; cảnh quyền lực lạnh và chắc; cảnh gia đình đúng vai vế.
- Không mặc định mọi lãnh đạo là "tổng tài".
TỪ VỰNG THAM KHẢO
- 总裁: tổng tài/chủ tịch/giám đốc tùy chức vụ.
- 董事长: chủ tịch hội đồng quản trị/chủ tịch.
- 老板: ông chủ/bà chủ/sếp.
- 少爷: thiếu gia/cậu chủ.
- 大小姐: đại tiểu thư/cô chủ.
- 夫人: phu nhân/bà chủ tùy người nói.
- 豪门: hào môn/gia tộc quyền thế.
- 婆婆: mẹ chồng; 岳母: mẹ vợ; 儿媳: con dâu; 女婿: con rể.
- 真千金: thiên kim thật/con gái ruột; 假千金: thiên kim giả.
- 继承人: người thừa kế; 股份: cổ phần; 遗产: tài sản thừa kế.
""",
    "costume_fantasy": BASE_TRANSCRIPT_PROMPT + """
PHONG CÁCH CỔ TRANG/HUYỀN HUYỄN
- Có chất cổ trang nhưng vẫn dễ hiểu, không dùng từ lóng hiện đại.
- Cảnh quyền lực uy nghiêm; chiến đấu gọn mạnh; bi thương sâu nhưng không dài dòng.
XƯNG HÔ THAM KHẢO
- Hoàng đế: trẫm - khanh/ngươi; thần tử: thần - bệ hạ.
- Sư đồ: sư phụ - đồ nhi/đệ tử; kẻ thù: ta - ngươi.
- Không dùng "tao - mày" trừ khi ngữ cảnh thật sự yêu cầu.
TỪ VỰNG THAM KHẢO
- 王爷: vương gia; 王妃: vương phi; 陛下: bệ hạ.
- 太子: thái tử; 皇后: hoàng hậu; 贵妃: quý phi.
- 师父: sư phụ; 徒儿: đồ nhi/đệ tử.
- 仙尊: tiên tôn; 魔尊: ma tôn; 宗门: tông môn/môn phái.
- 法术: pháp thuật; 灵力: linh lực; 修为: tu vi; 灵根: linh căn.
- 轮回: luân hồi; 前世: kiếp trước; 今生: kiếp này.
- 重生: trọng sinh/sống lại; 穿越: xuyên không; 渡劫: độ kiếp.
""",
}

CLEAN_REPLY_RE = re.compile(r"^[\"'`\s]+|[\"'`\s]+$")


def normalize_translation_style(style: str | None) -> str:
    style = (style or "general").strip()
    return style if style in TRANSCRIPT_TRANSLATION_PROMPTS else "general"


@dataclass(slots=True)
class TranslationResult:
    translated_title: str
    hashtags: list[str]
    raw_text: str


class Translator:
    DEFAULT_BATCH_SIZE = 30
    DEFAULT_CONTEXT_SIZE = 8

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or setup_logger("translator")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._sem = asyncio.Semaphore(settings.translation_concurrency)

    async def translate(self, source_title: str, style: str = "general") -> TranslationResult:
        style = normalize_translation_style(style)
        clean_title, original_tags = split_title_and_hashtags(source_title)
        if not clean_title:
            clean_title = source_title.strip()

        async with self._sem:
            raw = await self._translate_with_retry(clean_title, original_tags, style)

        line = normalize_text(raw).splitlines()[0] if raw else ""
        line = CLEAN_REPLY_RE.sub("", line).strip()

        translated_tags = self._extract_and_normalize_tags(line, original_tags)
        translated_title = self._strip_tags_from_title(line, translated_tags)
        if not translated_title:
            translated_title = line or clean_title

        return TranslationResult(
            translated_title=translated_title,
            hashtags=translated_tags,
            raw_text=raw,
        )

    async def translate_transcript_segments(
        self,
        segments: list[dict[str, Any]],
        style: str = "general",
        *,
        story_summary: str = "",
        scene_context: str = "",
        character_glossary: str = "",
        name_glossary: str = "",
        addressing_rules: str = "",
        batch_size: int | None = None,
        context_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Translate subtitle segments while preserving timing and segment order.

        Extra context parameters are optional, so existing callers remain compatible.
        Empty translated text is intentionally preserved because it may represent
        an ASR hallucination/no-speech segment.
        """
        style = normalize_translation_style(style)
        batch_size = max(1, batch_size or self.DEFAULT_BATCH_SIZE)
        context_size = max(0, context_size if context_size is not None else self.DEFAULT_CONTEXT_SIZE)

        clean_segments: list[dict[str, Any]] = []
        for index, seg in enumerate(segments, start=1):
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
            if end < start:
                end = start

            # Internal IDs are guaranteed unique and stable even when source IDs are
            # missing, duplicated or strings. The original output shape is preserved.
            speaker = str(seg.get("speaker") or seg.get("speaker_id") or seg.get("role") or "").strip()
            voice_type = str(seg.get("voice_type") or seg.get("gender") or seg.get("gender_hint") or "").strip()
            clean_segments.append({
                "id": index,
                "source_id": seg.get("id"),
                "start": start,
                "end": end,
                "duration": round(max(0.0, end - start), 3),
                "text": str(seg.get("text", "") or "").strip(),
                "speaker": speaker,
                "voice_type": voice_type,
                "original": seg,
            })

        if not clean_segments:
            return []

        translated_by_id: dict[int, str] = {}
        self.logger.info(
            "Translating transcript with style=%s (%s), segments=%s, batch_size=%s, context_size=%s",
            style,
            TRANSLATION_STYLE_LABELS[style],
            len(clean_segments),
            batch_size,
            context_size,
        )

        for batch_start in range(0, len(clean_segments), batch_size):
            batch_end = min(batch_start + batch_size, len(clean_segments))
            previous = clean_segments[max(0, batch_start - context_size):batch_start]
            current = clean_segments[batch_start:batch_end]
            following = clean_segments[batch_end:min(len(clean_segments), batch_end + context_size)]

            # Do not spend an API call on a batch containing only blank source segments.
            if not any(item["text"] for item in current):
                for item in current:
                    translated_by_id[item["id"]] = ""
                continue

            try:
                translated_items = await self._translate_segment_batch_with_retry(
                    previous=previous,
                    current=current,
                    following=following,
                    style=style,
                    story_summary=story_summary,
                    scene_context=scene_context,
                    character_glossary=character_glossary,
                    name_glossary=name_glossary,
                    addressing_rules=addressing_rules,
                )
            except Exception as exc:
                if len(current) <= 1:
                    raise
                self.logger.warning(
                    "Transcript batch translation failed; retrying one segment at a time: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                translated_items = []
                for offset, single in enumerate(current):
                    single_previous = clean_segments[max(0, batch_start + offset - context_size):batch_start + offset]
                    single_following = clean_segments[batch_start + offset + 1:min(len(clean_segments), batch_start + offset + 1 + context_size)]
                    try:
                        translated_items.extend(await self._translate_segment_batch_with_retry(
                            previous=single_previous,
                            current=[single],
                            following=single_following,
                            style=style,
                            story_summary=story_summary,
                            scene_context=scene_context,
                            character_glossary=character_glossary,
                            name_glossary=name_glossary,
                            addressing_rules=addressing_rules,
                        ))
                    except Exception as single_exc:
                        self.logger.warning(
                            "Segment translation failed id=%s; leaving it blank to avoid source-language TTS: %s: %s",
                            single["id"],
                            type(single_exc).__name__,
                            single_exc,
                        )
                        translated_items.append({"id": single["id"], "text": ""})
            for item in translated_items:
                translated_by_id[int(item["id"])] = str(item.get("text", "")).strip()

        result: list[dict[str, Any]] = []
        for seg in clean_segments:
            internal_id = seg["id"]
            if internal_id in translated_by_id:
                # Empty text is valid and must not fall back to hallucinated source text.
                vi_text = translated_by_id[internal_id]
            else:
                vi_text = ""
                self.logger.warning(
                    "Missing translated segment id=%s; leaving it blank to avoid source-language TTS.",
                    internal_id,
                )

            output_item = {
                "start": seg["start"],
                "end": seg["end"],
                "text": vi_text,
            }
            # Preserve source id only when the caller originally supplied one.
            if seg["source_id"] is not None:
                output_item["id"] = seg["source_id"]
            if seg.get("speaker"):
                output_item["speaker"] = seg["speaker"]
            if seg.get("voice_type"):
                output_item["voice_type"] = seg["voice_type"]
            result.append(output_item)

        return result

    async def _translate_with_retry(
        self,
        clean_title: str,
        original_tags: list[str],
        style: str,
    ) -> str:
        last_error: Exception | None = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=12),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self.client.responses.create(
                        model=self.settings.openai_model,
                        instructions=TITLE_TRANSLATION_PROMPTS[style],
                        input=(
                            f"NGUYÊN VĂN:\n{clean_title}\n\n"
                            f"HASHTAG GỐC:\n{' '.join('#' + t for t in original_tags) or '(không có)'}"
                        ),
                    )
                    text = response.output_text.strip()
                    if not text:
                        raise ValueError("OpenAI returned empty title translation")
                    return text
                except Exception as exc:
                    last_error = exc
                    self.logger.warning(
                        "Dịch tiêu đề lỗi (sẽ retry): %s: %s",
                        type(exc).__name__,
                        exc,
                    )
                    raise
        if last_error:
            raise last_error
        raise RuntimeError("Title translation failed")

    async def _translate_segment_batch_with_retry(
        self,
        *,
        previous: list[dict[str, Any]],
        current: list[dict[str, Any]],
        following: list[dict[str, Any]],
        style: str,
        story_summary: str,
        scene_context: str,
        character_glossary: str,
        name_glossary: str,
        addressing_rules: str,
    ) -> list[dict[str, Any]]:
        expected_ids = [int(item["id"]) for item in current]
        payload = {
            "STORY_SUMMARY": story_summary.strip() or "Không được cung cấp.",
            "SCENE_CONTEXT": scene_context.strip() or "Không được cung cấp.",
            "CHARACTER_GLOSSARY": character_glossary.strip() or "Không được cung cấp.",
            "NAME_GLOSSARY": name_glossary.strip() or "Không được cung cấp.",
            "ADDRESSING_RULES": addressing_rules.strip() or "Không được cung cấp.",
            "SPEAKER_ROLE_RULES": (
                "If a segment contains speaker, voice_type or gender_hint metadata, keep the same character role "
                "and choose Vietnamese pronouns consistently. Treat male/female as hints, not hard facts. "
                "Do not invent a speaker when metadata is empty."
            ),
            "PREVIOUS_SEGMENTS": self._segment_payload(previous),
            "CURRENT_SEGMENTS": self._segment_payload(current),
            "NEXT_SEGMENTS": self._segment_payload(following),
        }

        last_error: Exception | None = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=12),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    async with self._sem:
                        response = await self.client.responses.create(
                            model=self.settings.openai_model,
                            instructions=TRANSCRIPT_TRANSLATION_PROMPTS[style],
                            input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        )
                    text = response.output_text.strip()
                    if not text:
                        raise ValueError("OpenAI returned empty transcript translation")

                    parsed = self._parse_segment_translation(text)
                    return self._validate_segment_translation(parsed, expected_ids)
                except Exception as exc:
                    last_error = exc
                    self.logger.warning(
                        "Dịch transcript lỗi (sẽ retry): %s: %s",
                        type(exc).__name__,
                        exc,
                    )
                    raise

        if last_error:
            raise last_error
        raise RuntimeError("Transcript translation failed")

    @staticmethod
    def _segment_payload(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for item in segments:
            row = {
                "id": int(item["id"]),
                "start": item["start"],
                "end": item["end"],
                "duration": item["duration"],
                "text": item["text"],
            }
            if item.get("speaker"):
                row["speaker"] = item["speaker"]
            if item.get("voice_type"):
                row["voice_type"] = item["voice_type"]
            payload.append(row)
        return payload

    @staticmethod
    def _parse_segment_translation(raw: str) -> list[dict[str, Any]]:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Greedy extraction is acceptable here because the expected root is one array.
            match = re.search(r"\[.*\]", text, flags=re.DOTALL)
            if not match:
                raise ValueError("Transcript response does not contain a JSON array")
            data = json.loads(match.group(0))

        if not isinstance(data, list):
            raise ValueError("Transcript translation response is not a JSON array")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _validate_segment_translation(
        items: list[dict[str, Any]],
        expected_ids: list[int],
    ) -> list[dict[str, Any]]:
        by_id: dict[int, str] = {}
        for item in items:
            if "id" not in item or "text" not in item:
                continue
            try:
                item_id = int(item["id"])
            except (TypeError, ValueError):
                continue
            if item_id in by_id:
                raise ValueError(f"Duplicate translated segment id={item_id}")
            by_id[item_id] = str(item.get("text", "") or "").strip()

        expected_set = set(expected_ids)
        actual_set = set(by_id)
        missing = expected_set - actual_set
        unexpected = actual_set - expected_set
        if missing or unexpected:
            raise ValueError(
                f"Invalid translated ids; missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )

        return [{"id": item_id, "text": by_id[item_id]} for item_id in expected_ids]

    @staticmethod
    def _extract_and_normalize_tags(text: str, original_tags: list[str]) -> list[str]:
        tags = re.findall(r"#([^\s#]+)", text or "")
        if not tags:
            tags = original_tags
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            safe = normalize_hashtag(tag)
            if safe and safe not in seen:
                seen.add(safe)
                result.append(safe)
        return result

    @staticmethod
    def _strip_tags_from_title(text: str, hashtags: list[str]) -> str:
        result = text
        for tag in hashtags:
            # Match both normalized and raw hashtag-like forms conservatively.
            result = re.sub(rf"#?{re.escape(tag)}", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+", " ", result).strip(" -_#")
        return result

