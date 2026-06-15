from __future__ import annotations
import re
from datetime import datetime
import asyncio
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.renamer import build_output_path
import aiohttp
import requests
from playwright.sync_api import sync_playwright
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.logger import setup_logger
from app.utils import (
    ensure_dir,
    now_iso,
    sha256_file,
)
import subprocess
import shlex


@dataclass(slots=True)
class VideoMeta:
    aweme_id: str
    title: str
    hashtags: list[str]
    create_time: int
    video_url: str
    webpage_url: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:

        return {
            "aweme_id": self.aweme_id,
            "title": self.title,
            "hashtags": self.hashtags,
            "create_time": self.create_time,
            "video_url": self.video_url,
            "webpage_url": self.webpage_url,
            "raw": self.raw,
        }


class DouyinDownloader:

    def __init__(
        self,
        settings: Settings,
        logger=None
    ) -> None:

        self.settings = settings
        self.logger = logger or setup_logger("douyin")

    async def crawl_profile(
        self,
        profile_url: str,
        target_month: str | None = None
    ) -> list[VideoMeta]:

        ensure_dir(
            self.settings.downloads_dir / "_tmp"
        )

        return await asyncio.to_thread(
            self._crawl_profile_sync,
            profile_url,
            target_month
        )

    def _crawl_profile_sync(
        self,
        profile_url: str,
        target_month: str | None = None
    ) -> list[VideoMeta]:

        self.logger.info(
            f"[cyan]Đang crawl profile:[/cyan] "
            f"{profile_url}"
        )

        videos: list[VideoMeta] = []

        with sync_playwright() as p:

            context = p.chromium.launch_persistent_context(
                user_data_dir="pw_profile",
                headless=False,
            )

            page = context.new_page()

            page.goto(
                profile_url,
                wait_until="domcontentloaded",
                timeout=120000
            )

            self.logger.info(
                "[green]Đợi load profile...[/green]"
            )

            time.sleep(5)
            if target_month:

                try:
                    parts = target_month.split("-")
                    if len(parts) != 2:
                        raise ValueError("target_month must be YYYY-MM")

                    year, month = parts
                    year = year.strip()
                    month = str(int(month.strip()))
                    if len(year) != 4 or not year.isdigit():
                        raise ValueError("target_month year must be YYYY")

                    self.logger.info(
                        f"[cyan]Lọc tháng:[/cyan] "
                        f"{target_month}"
                    )

                    # hover 日期筛选
                    filter_btn = page.locator(
                        "text=日期筛选"
                    )

                    filter_btn.hover()

                    self.logger.info(
                        "[green]Hover 日期筛选[/green]"
                    )

                    time.sleep(2)

                    # hover year
                    year_text = f"{year}年"

                    year_locator = page.locator(
                        f'text="{year_text}"'
                    )

                    year_locator.first.hover()

                    self.logger.info(
                        f"[green]Hover {year_text}[/green]"
                    )

                    time.sleep(2)

                    # month render sau hover
                    month_text = f"{month.zfill(2)}月"

                    month_locator = page.locator(
                        f'text="{month_text}"'
                    )

                    month_locator.first.click(
                        timeout=10000
                    )

                    self.logger.info(
                        f"[green]Đã click {month_text}[/green]"
                    )

                    time.sleep(5)

                    self.logger.info(
                        "[green]Đã filter xong[/green]"
                    )

                except Exception as e:

                    self.logger.error(
                        f"Lỗi filter month: {e}"
                    )

                    return []
            seen = set()

            max_scroll = (
                10
                if target_month
                else 50
            )

            for i in range(max_scroll):

                self.logger.info(
                    f"[cyan]Scrolling[/cyan] "
                    f"{i+1}/{max_scroll}"
                )

                page.mouse.wheel(0, 15000)

                time.sleep(2)

                video_links = page.evaluate("""
                () => {

                    const anchors = Array.from(
                        document.querySelectorAll(
                            '[data-e2e="user-post-list"] a'
                        )
                    );

                    return anchors.map(a => {

                        return {
                            href: a.href,
                            title: a.innerText || ""
                        };

                    });
                }
                """)

                added = 0

                for item in video_links:

                    href = item["href"]
                    title = item["title"]

                    title = title.split("\\n")[-1].strip()
                    title = re.sub(
                        r"^\d+(\.\d+)?[KWM万]?\s*",
                        "",
                        title
                    )

                    full_url = href.split("?")[0]

                    if "/note/" in full_url:

                        self.logger.info(
                            f"[yellow]Bỏ qua note:[/yellow] "
                            f"{full_url}"
                        )

                        continue

                    aweme_id = (
                        full_url.rstrip("/")
                        .split("/")[-1]
                    )

                    if aweme_id in seen:
                        continue

                    seen.add(aweme_id)

                    try:


                        if not title:
                            title = aweme_id

                        if not title:
                            title = aweme_id

                        videos.append(
                            VideoMeta(
                                aweme_id=aweme_id,
                                title=title,
                                hashtags=[],
                                create_time=int(time.time()),
                                video_url=full_url,
                                webpage_url=full_url,
                                raw={
                                    "href": full_url
                                },
                            )
                        )

                        added += 1

                    except Exception as e:

                        self.logger.error(
                            f"Lỗi parse video: {e}"
                        )

                self.logger.info(
                    f"[green]Tổng video hiện tại:[/green] "
                    f"{len(videos)} | "
                    f"mới thêm: {added}"
                )

                if added == 0 and i > 5:

                    self.logger.info(
                        "[yellow]Không có video mới -> dừng scroll[/yellow]"
                    )

                    break

            context.close()

        videos.reverse()

        self.logger.info(
            f"[green]Đã crawl được "
            f"{len(videos)} video[/green]"
        )

        return videos

    async def probe_url(self, url: str) -> bool:

        timeout = aiohttp.ClientTimeout(total=15)

        try:

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.head(
                    url,
                    allow_redirects=True
                ) as resp:

                    return 200 <= resp.status < 500

        except Exception:

            return False

    async def download_video(
        self,
        video: VideoMeta,
        target_dir: Path,
        index: int,
        translated_title: str,
        hashtags: list[str],
        *,
        progress_callback=None,
    ) -> Path:

        ensure_dir(target_dir)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(
                self.settings.max_retries
            ),
            wait=wait_exponential(
                multiplier=1,
                min=1,
                max=10
            ),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):

            with attempt:

                output_path = await asyncio.to_thread(
                   self._download_with_playwright,
                    video,
                    target_dir,
                    index,
                    translated_title,
                    hashtags,
                )

                return output_path

        raise Exception("Download failed")

    def _download_with_playwright(
        self,
        video: VideoMeta,
        target_dir: Path,
        index: int,
        translated_title: str,
        hashtags: list[str],
    ) -> Path:

        video_page_url = video.webpage_url

        real_video_url = None
        real_audio_url = None

        with sync_playwright() as p:

            context = p.chromium.launch_persistent_context(
                user_data_dir="pw_profile",
                headless=False,
            )

            try:

                page = context.new_page()

                # =========================
                # RESPONSE HANDLER
                # =========================
                def handle_response(response):
                    nonlocal real_video_url, real_audio_url

                    try:
                        url = response.url.lower()
                        raw_url = response.url
                        content_type = response.headers.get("content-type", "").lower()

                        if "text/html" in content_type:
                            return

                        # Bỏ watermark
                        if "playwm" in url:
                            return

                        # Bỏ tài nguyên tĩnh rõ ràng
                        if any(x in url for x in [".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff"]):
                            return

                        try:
                            size = int(response.headers.get("content-length", "0"))
                        except Exception:
                            size = 0

                        # ── AUDIO ──
                        is_audio = "audio" in url or "audio" in content_type
                        if is_audio:
                            if size > 0 and size < 10_000:
                                return
                            if real_audio_url is None:
                                self.logger.info(f"[magenta]Audio found:[/magenta] {raw_url[:150]}")
                                real_audio_url = raw_url
                            return

                        # ── VIDEO ──
                        # Mở rộng pattern nhận diện
                        is_video_url = any(x in url for x in [
                            ".mp4", "/play/", "video", "/aweme/", "snssdk"
                        ])
                        is_video_ct = any(x in content_type for x in [
                            "video", "octet-stream", "application/mp4"
                        ])

                        if not is_video_url and not is_video_ct:
                            return

                        # ✅ Hạ threshold xuống 100KB thay vì 500KB
                        if size > 0 and size < 100_000:
                            return

                        if real_video_url is None:
                            self.logger.info(f"[green]Video found:[/green] {raw_url[:150]}")
                            real_video_url = raw_url

                    except Exception as e:
                        self.logger.error(f"handle_response error: {e}")
                # =========================
                # ATTACH LISTENER
                # =========================
                page.on(
                    "response",
                    handle_response
                )

                self.logger.info(
                    f"[cyan]Mở video:[/cyan]\n"
                    f"{video_page_url}"
                )

                # =========================
                # OPEN VIDEO PAGE
                # =========================
                page.goto(
                    video_page_url,
                    wait_until="domcontentloaded",
                    timeout=120_000,
                )

                # click play vài lần để trigger stream
                for _ in range(5):

                    if real_video_url and real_audio_url:
                        break

                    try:
                        page.mouse.click(500, 500)
                    except Exception:
                        pass

                    time.sleep(2)

                if not real_video_url:

                    raise Exception(
                        "Không bắt được real video stream"
                    )

                self.logger.info(
                    f"[green]REAL VIDEO URL:[/green]\n"
                    f"{real_video_url[:150]}"
                )

                if real_audio_url:

                    self.logger.info(
                        f"[magenta]REAL AUDIO URL:[/magenta]\n"
                        f"{real_audio_url[:150]}"
                    )

                else:

                    self.logger.info(
                        "[yellow]Không có audio track riêng "
                        "-> video đã có audio muxed sẵn[/yellow]"
                    )

                # =========================
                # OUTPUT PATH
                # =========================
                output_path = build_output_path(
                    base_dir=target_dir,
                    index=index,
                    date_folder="",
                    translated_title=translated_title,
                    hashtags=hashtags,
                    source_suffix=".mp4",
                    max_filename_len=self.settings.max_filename_len,
                )

                # =========================
                # COOKIES
                # =========================
                cookies = context.cookies()

                cookie_header = "; ".join(
                    [
                        f"{c['name']}={c['value']}"
                        for c in cookies
                    ]
                )

                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64)"
                    ),
                    "Referer": "https://www.douyin.com/",
                    "Cookie": cookie_header,
                }

                # =========================
                # HELPER: DOWNLOAD FILE
                # =========================
                def _stream_download(url: str, dest: Path) -> None:

                    with requests.get(
                        url,
                        headers=headers,
                        stream=True,
                        timeout=120,
                    ) as r:

                        r.raise_for_status()

                        total = int(
                            r.headers.get("content-length", 0)
                        )

                        downloaded = 0
                        last_logged = -1

                        with open(dest, "wb") as f:

                            for chunk in r.iter_content(
                                chunk_size=1024 * 512
                            ):

                                if not chunk:
                                    continue

                                f.write(chunk)
                                downloaded += len(chunk)

                                if total > 0:

                                    pct = int(
                                        downloaded * 100 / total
                                    )

                                    if (
                                        pct % 10 == 0
                                        and pct != last_logged
                                    ):

                                        self.logger.info(
                                            f"[blue]Download[/blue] "
                                            f"{pct}%"
                                        )

                                        last_logged = pct

                # =========================
                # DOWNLOAD VIDEO TRACK
                # =========================
                self.logger.info(
                    "[cyan]Đang tải video track...[/cyan]"
                )

                content_type_video = ""

                with requests.get(
                    real_video_url,
                    headers=headers,
                    stream=True,
                    timeout=120,
                ) as r:

                    r.raise_for_status()

                    content_type_video = (
                        r.headers.get("content-type", "").lower()
                    )

                    self.logger.info(
                        f"[cyan]Content-Type video:[/cyan] "
                        f"{content_type_video}"
                    )

                    video_tmp = (
                        output_path.with_suffix(".video_tmp.mp4")
                        if real_audio_url
                        else output_path
                    )

                    if "video" not in content_type_video:

                        self.logger.warning(
                            f"Content-Type not video ({content_type_video}); trying Playwright authenticated download"
                        )

                        try:
                            self._download_with_playwright_request(
                                context,
                                real_video_url,
                                video_tmp,
                                referer=video_page_url,
                            )
                        except Exception as playwright_error:
                            self.logger.warning(
                                f"Playwright authenticated download failed: {playwright_error}"
                            )
                            try:
                                return self._download_with_ytdlp(video_page_url, output_path, cookie_header=cookie_header)
                            except Exception as ytdlp_error:
                                raise Exception(
                                    "Cannot download Douyin video stream. "
                                    f"requests content-type={content_type_video}; "
                                    f"playwright_error={playwright_error}; "
                                    f"yt_dlp_error={ytdlp_error}"
                                ) from ytdlp_error

                    else:
                        total = int(
                            r.headers.get("content-length", 0)
                        )

                        downloaded = 0
                        last_logged = -1

                        with open(video_tmp, "wb") as f:

                            for chunk in r.iter_content(
                                chunk_size=1024 * 512
                            ):

                                if not chunk:
                                    continue

                                f.write(chunk)
                                downloaded += len(chunk)

                                if total > 0:

                                    pct = int(
                                        downloaded * 100 / total
                                    )

                                    if (
                                        pct % 10 == 0
                                        and pct != last_logged
                                    ):

                                        self.logger.info(
                                            f"[blue]Download video[/blue] "
                                            f"{pct}%"
                                        )

                                        last_logged = pct

                # =========================
                # DOWNLOAD + MERGE AUDIO
                # =========================
                if real_audio_url:

                    audio_tmp = output_path.with_suffix(
                        ".audio_tmp.m4a"
                    )

                    self.logger.info(
                        "[cyan]Đang tải audio track...[/cyan]"
                    )

                    _stream_download(real_audio_url, audio_tmp)

                    self.logger.info(
                        "[cyan]Đang merge video + audio...[/cyan]"
                    )

                    import subprocess

                    result = subprocess.run(
                        [
                            "ffmpeg", "-y",
                            "-i", str(video_tmp),
                            "-i", str(audio_tmp),
                            "-map", "0:v:0",
                            "-map", "1:a:0",
                            "-c:v", "libx264",
                            "-preset", "veryfast",
                            "-crf", "20",
                            "-profile:v", "high",
                            "-pix_fmt", "yuv420p",
                            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                            "-c:a", "aac",
                            "-b:a", "160k",
                            "-movflags", "+faststart",
                            "-shortest",
                            
str(output_path),
                        ],
                        capture_output=True,
                        text=True,
                    )

                    # dọn file tạm
                    video_tmp.unlink(missing_ok=True)
                    audio_tmp.unlink(missing_ok=True)

                    if result.returncode != 0:

                        self.logger.error(
                            f"[red]ffmpeg error:[/red]\n"
                            f"{result.stderr[-500:]}"
                        )

                        raise Exception(
                            f"ffmpeg merge thất bại: "
                            f"{result.stderr[-200:]}"
                        )

                    self.logger.info(
                        "[green]Merge video + audio xong![/green]"
                    )

                self.logger.info(
                    f"[green]Tải xong:[/green]\n"
                    f"{output_path.name}"
                )

                return output_path

            finally:

                context.close()
    def _download_with_playwright_request(self, context, url: str, dest: Path, referer: str) -> Path:
        """Download a captured Douyin stream with the same Playwright browser context."""
        dest = Path(dest)
        ensure_dir(dest.parent)
        response = context.request.get(
            url,
            headers={
                "Referer": referer,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
            timeout=120_000,
        )
        content_type = (response.headers.get("content-type") or "").lower()
        if not response.ok:
            raise Exception(f"HTTP {response.status} while downloading stream; content-type={content_type}")
        if "video" not in content_type and "octet-stream" not in content_type and "mp4" not in content_type:
            preview = response.text()[:200] if "text" in content_type or "html" in content_type else ""
            raise Exception(f"not a video response: content-type={content_type}; preview={preview!r}")
        body = response.body()
        if not body:
            raise Exception("empty video response body")
        dest.write_bytes(body)
        self.logger.info(f"[green]Playwright authenticated download OK:[/green] {dest.name} ({dest.stat().st_size} bytes)")
        return dest
    def _download_with_ytdlp(self, page_url: str, output_path: Path, cookie_header: str = "") -> Path:
        """Fallback downloader using yt-dlp. Returns final Path on success."""

        ensure_dir(output_path.parent)

        out_template = str(output_path.with_suffix(".%(ext)s"))

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "bv*+ba/best",
            "--merge-output-format",
            "mp4",
            "--add-header",
            "Referer:https://www.douyin.com/",
            "--add-header",
            "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "-o",
            out_template,
            page_url,
        ]
        if cookie_header:
            cmd[11:11] = ["--add-header", f"Cookie:{cookie_header}"]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except FileNotFoundError as e:
            raise Exception("Python executable not found for yt-dlp fallback") from e

        if proc.returncode != 0:
            raise Exception(f"yt-dlp failed: {proc.stderr[-1000:]}")

        # Find the downloaded file (yt-dlp appends an extension)
        candidates = list(output_path.parent.glob(output_path.stem + "*"))
        if not candidates:
            raise Exception("yt-dlp did not produce output file")

        downloaded = candidates[0]

        # If filename differs, move/rename to desired output_path
        if downloaded.resolve() != output_path.resolve():
            downloaded.replace(output_path)

        return output_path
    async def move_and_finalize(
        self,
        source: Path,
        target: Path,
        *,
        make_checksum: bool = False,
    ) -> dict[str, Any]:

        ensure_dir(target.parent)

        if target.exists():
            target.unlink()

        await asyncio.to_thread(
            shutil.move,
            str(source),
            str(target)
        )

        result = {
            "path": str(target),
            "size": target.stat().st_size,
            "updated_at": now_iso(),
        }

        if make_checksum:

            result["sha256"] = (
                await asyncio.to_thread(
                    sha256_file,
                    target
                )
            )

        return result
