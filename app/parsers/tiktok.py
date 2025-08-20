import aiohttp
import aiofiles
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.config import settings
from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoResponse, SVideoDownload, SVideoFormat
from app.utils.helpers import remove_all_spec_chars
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, convert_to_mp3


@dataclass
class TikTokVideo:
    video_url: str
    audio_url: str
    title: str
    author: str
    duration: int
    preview_url: str
    video_size: int
    audio_size: int


class TikTokParser(BaseParser):
    def __init__(self, url: str):
        self.url = url if ('?lang=' in url or '&lang=' in url) else (url + ('&lang=en' if '?' in url else '?lang=en'))
        self.api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.tikwm.com/",
            "Accept": "application/json, text/plain, */*",
        }
        self.api_url = f"https://www.tikwm.com/api/?url={self.url}&hd=1"

    async def _get_video_info(self):
        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            async with session.get(self.api_url) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        if payload.get("code") != 0 or not payload.get("data"):
            raise ValueError("TikTok: cannot parse video url")

        data = payload["data"]
        video_url: Optional[str] = data.get("hdplay") or data.get("wmplay") or data.get("play")
        audio_url: Optional[str] = data.get("music")
        title: str = data.get("title", "tiktok_video")
        if len(title) > 50:
            title = title[:50] + "..."
        duration: int = int(data.get("duration", 0))
        cover: Optional[str] = data.get("cover") or data.get("origin_cover")
        author: str = "tiktok"
        author_obj = data.get("author")
        if isinstance(author_obj, dict):
            author = author_obj.get("unique_id") or author_obj.get("nickname") or author
        elif isinstance(author_obj, str) and author_obj:
            author = author_obj

        video_size = 0
        audio_size = 0
        async with aiohttp.ClientSession(headers={"User-Agent": self.api_headers["User-Agent"]}) as hs:
            if video_url:
                async with hs.head(video_url, allow_redirects=True) as h:
                    if h.status < 400 and h.headers.get("Content-Length"):
                        video_size = int(h.headers["Content-Length"])

            if audio_url:
                async with hs.head(audio_url, allow_redirects=True) as ah:
                    if ah.status < 400 and ah.headers.get("Content-Length"):
                        audio_size = int(ah.headers["Content-Length"])

            if not audio_size and duration:
                audio_size = int((128000 / 8) * duration)

        preview_url = None
        if cover:
            try:
                preview_url = await save_preview_on_s3(cover, title, author)
            except Exception:
                preview_url = cover

        return TikTokVideo(video_url, audio_url, title, author, duration, preview_url, video_size, audio_size)

    async def get_formats(self) -> SVideoResponse:
        video = await self._get_video_info()

        formats = [
            SVideoFormat(quality="MP4", video_format_id="video", audio_format_id="audio", filesize=video.video_size),
            SVideoFormat(quality="Audio only", video_format_id="", audio_format_id="audio", filesize=video.audio_size),
        ]

        return SVideoResponse(
            url=self.url,
            title=video.title,
            author=video.author,
            preview_url=video.preview_url,
            duration=video.duration,
            formats=formats,
        )

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)

        video = await self._get_video_info()
        is_audio_only = not download_video.video_format_id
        extension = ".mp3" if is_audio_only else ".mp4"
        out_dir = Path(settings.DOWNLOAD_FOLDER) / remove_all_spec_chars(video.author)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}_{remove_all_spec_chars(video.title)}{extension}"

        source_url = video.audio_url if is_audio_only and video.audio_url else video.video_url
        if not source_url:
            raise ValueError("TikTok: no suitable media stream")

        temp_path = out_path
        if is_audio_only and video.audio_url is None:
            temp_path = out_path.with_suffix(".temp")

        task.filepath = temp_path
        task.video_status.description = "Downloading audio track" if is_audio_only else "Downloading video track"
        await redis_cache.set_download_task(task)

        async with aiohttp.ClientSession(headers={"User-Agent": self.api_headers["User-Agent"]}) as dl_sess:
            async with dl_sess.get(source_url) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                read = 0
                last_t = time.time()
                last_bytes = 0
                async with aiofiles.open(temp_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(1024 * 64):
                        if not chunk:
                            break
                        await f.write(chunk)
                        read += len(chunk)
                        now = time.time()
                        dt = max(1e-3, now - last_t)
                        speed = float(max(0, read - last_bytes)) / dt
                        last_t = now
                        last_bytes = read
                        if total:
                            task.video_status.percent = int(read / total * 100)
                            remain = max(0, total - read)
                            task.video_status.speed_bps = speed
                            task.video_status.eta_seconds = int(remain / speed) if speed > 0 else None
                        await redis_cache.set_download_task(task)
                        if await redis_cache.is_task_canceled(task_id):
                            raise DownloadUserCanceledException()

        if is_audio_only and video.audio_url is None:
            task.video_status.description = "Converting to MP3"
            await redis_cache.set_download_task(task)
            await convert_to_mp3(temp_path.as_posix(), out_path.as_posix())
            temp_path.unlink(missing_ok=True)

        task.filepath = out_path

        post_process = PostPrecess(task, download_video)
        await post_process.process()

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task)
