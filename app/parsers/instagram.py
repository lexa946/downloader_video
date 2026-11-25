import json
import logging
import asyncio
import aiofiles
import time
from pathlib import Path

from fastapi import HTTPException
import aiohttp
from dataclasses import dataclass
from bs4 import BeautifulSoup

from app.config import settings
from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask

from app.parsers.base import BaseParser
from app.schemas.main import SVideoResponse, SVideoDownload, SVideoFormat
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, convert_to_mp3
import re


@dataclass
class InstagramVideo:
    title: str
    content_url: str
    preview_url: str
    duration: int
    quality: str
    size: int
    author: str

    @classmethod
    def from_item(cls, item: dict):
        stream = next(v for v in item["video_versions"] if v.get("url"))
        author = (item.get("user") or {}).get("username") or "instagram_user"
        author = re.sub(r"[^A-Za-z0-9._]", "_", author).strip(".") or "instagram_user"
        code = item["code"]
        images = (item.get("image_versions2") or {}).get("candidates") or []
        quality = f"{stream['width']}x{stream['height']}" if stream.get("width") and stream.get("height") else "unknown"
        duration = item.get("video_duration") or 0
        if not duration and item.get("video_dash_manifest"):
            manifest = BeautifulSoup(item["video_dash_manifest"], features="xml")
            period = manifest.find("Period")
            match = re.fullmatch(r"PT([0-9.]+)S", period.get("duration", "")) if period else None
            if match:
                duration = float(match[1])
        return cls(f"video_by_{author}_{code}.mp4", stream["url"], images[0].get("url", "") if images else "",
                   int(duration), quality, 0, author)


def find_video_item(value, shortcode):
    if isinstance(value, dict):
        if value.get("code") == shortcode and any(v.get("url") for v in value.get("video_versions") or []):
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        found = find_video_item(child, shortcode)
        if found:
            return found


class InstagramParser(BaseParser):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, url):
        self.url = url
        self._response_text = None

        self._asset_headers = dict(self.headers)
        self._asset_headers["Referer"] = self.url

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers) as response:
                response.raise_for_status()
                response_text = await response.text()

            video = self._parse_video_attributes(response_text, self.url)
            download_path = Path(settings.DOWNLOAD_FOLDER) / video.author / f"{task_id}_video_{video.title}"
            download_path.parent.mkdir(parents=True, exist_ok=True)

            is_audio_only = not download_video.video_format_id

            task.video_status.description = "Downloading video track" if not is_audio_only else "Downloading audio track"
            await redis_cache.set_download_task(task)
            async with session.get(video.content_url, headers=self._asset_headers) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('Content-Length', 0))
                bytes_read = 0
                last_t = time.time()
                last_bytes = 0
                temp_path = download_path

                if is_audio_only:
                    temp_path = download_path.with_suffix('.temp')

                task.filepath = temp_path
                await redis_cache.set_download_task(task)
                async with aiofiles.open(temp_path, 'wb') as f:
                    while True:
                        if await redis_cache.is_task_canceled(task_id):
                            raise DownloadUserCanceledException()
                        chunk = await response.content.read(8192)  # читаем по 8 КБ
                        if not chunk:
                            break
                        await f.write(chunk)
                        bytes_read += len(chunk)
                        now = time.time()
                        dt = max(1e-3, now - last_t)
                        speed = float(max(0, bytes_read - last_bytes)) / dt  # bytes/sec
                        last_t = now
                        last_bytes = bytes_read
                        if total_size:
                            task.video_status.percent = int((bytes_read / total_size) * 100)
                            remain = max(0, total_size - bytes_read)
                            task.video_status.speed_bps = speed
                            task.video_status.eta_seconds = int(remain / speed) if speed > 0 else None
                        await redis_cache.set_download_task(task)

                if is_audio_only:
                    task.video_status.description = "Converting to MP3"
                    await redis_cache.set_download_task(task)
                    mp3_path = download_path.with_suffix('.mp3')
                    await asyncio.to_thread(convert_to_mp3,
                                            temp_path.as_posix(),
                                            mp3_path.as_posix()
                                            )
                    temp_path.unlink(missing_ok=True)
                    task.filepath = mp3_path
                else:
                    task.filepath = temp_path

        post_process = PostPrecess(task, download_video)
        await post_process.process()

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task)

    @staticmethod
    def _parse_video_attributes(content: str, requested_url: str = "") -> InstagramVideo:
        soup = BeautifulSoup(content, features="lxml")

        canonical_tag = soup.select_one("link[rel='canonical']")
        if canonical_tag and canonical_tag.get("href"):
            canonical_url = canonical_tag.get("href", "")
        else:
            og_url_tag = soup.select_one("meta[property='og:url']")
            canonical_url = og_url_tag.get("content", "") if og_url_tag and og_url_tag.get("content") else ""

        match = re.search(r"/(?:reels?|p)/([A-Za-z0-9_-]+)(?:[/?#]|$)", requested_url)
        if not match:
            match = re.search(r"/(?:reels?|p)/([A-Za-z0-9_-]+)(?:[/?#]|$)", canonical_url)
        shortcode = match[1] if match else None

        for script in soup.select("script[type='application/json']"):
            if not shortcode or '"video_versions"' not in script.text:
                continue
            try:
                payload = json.loads(script.text)
            except json.JSONDecodeError:
                continue
            item = find_video_item(payload, shortcode)
            if item:
                return InstagramVideo.from_item(item)

        og_video = None
        for prop in [
            "meta[property='og:video:secure_url']",
            "meta[property='og:video:url']",
            "meta[property='og:video']",
        ]:
            tag = soup.select_one(prop)
            if tag and tag.get("content"):
                og_video = tag.get("content")
                break

        if not og_video:
            raise HTTPException(422, "Instagram не предоставил видео для этой ссылки.")

        og_image = soup.select_one("meta[property='og:image']")
        preview = og_image.get("content", "") if og_image else ""

        og_desc = soup.select_one("meta[property='og:description']")
        author = "instagram_user"
        if og_desc and og_desc.get("content"):
            m = re.search(r"@([A-Za-z0-9._]+)", og_desc.get("content", ""))
            if m:
                author = m.group(1)

        width = soup.select_one("meta[property='og:video:width']")
        height = soup.select_one("meta[property='og:video:height']")
        try:
            vw = int(width.get("content")) if width and width.get("content") else 0
            vh = int(height.get("content")) if height and height.get("content") else 0
        except Exception:
            vw, vh = 0, 0
        quality = f"{vw}x{vh}" if vw and vh else "unknown"

        dur_tag = soup.select_one("meta[property='og:video:duration']")
        try:
            duration = int(dur_tag.get("content")) if dur_tag and dur_tag.get("content") else 0
        except Exception:
            duration = 0

        title = f"video_by_{author}.mp4"
        if shortcode:
            title = f"video_by_{author}_{shortcode}.mp4"

        return InstagramVideo(title, og_video, preview, duration, quality, 0, author)

    async def get_formats(self) -> SVideoResponse:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers) as response:
                response.raise_for_status()
                response_text = await response.text()

        video = self._parse_video_attributes(response_text, self.url)

        if not video.size:
            try:
                async with aiohttp.ClientSession() as session2:
                    async with session2.head(video.content_url, headers=self._asset_headers) as head_resp:
                        clen = head_resp.headers.get('Content-Length') or head_resp.headers.get('content-length')
                        if clen:
                            video.size = int(clen)
            except Exception:
                pass

        preview_url = video.preview_url
        if preview_url:
            try:
                preview_url = await save_preview_on_s3(preview_url, video.title, video.author)
            except Exception:
                logging.getLogger(__name__).warning("Could not cache Instagram preview", exc_info=True)

        available_formats = [
            SVideoFormat(
                **{
                    "quality": video.quality,
                    "video_format_id": "video",
                    "audio_format_id": "audio",
                    "filesize": video.size,
                }
            ),
            SVideoFormat(
                **{
                    "quality": "Audio only",
                    "video_format_id": "",
                    "audio_format_id": "audio",
                    "filesize": video.size // 4,
                }
            )
        ]
        return SVideoResponse(
            url=self.url,
            title=video.title,
            author=video.author,
            preview_url=preview_url,
            duration=video.duration,
            formats=available_formats,
        )
