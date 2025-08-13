import aiohttp
import aiofiles
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoResponse, SVideoDownload, SVideoFormat
from app.utils.helpers import remove_all_spec_chars
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, convert_to_mp3


TIKTOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


class TikTokParser(BaseParser):
    def __init__(self, url: str):
        self.url = url if ('?lang=' in url or '&lang=' in url) else (url + ('&lang=en' if '?' in url else '?lang=en'))

    async def get_formats(self) -> SVideoResponse:
        headers_tw = {
            **TIKTOK_HEADERS,
            "Referer": "https://www.tikwm.com/",
            "Accept": "application/json, text/plain, */*",
        }
        api_url = f"https://www.tikwm.com/api/?url={self.url}&hd=1"

        async with aiohttp.ClientSession(headers=headers_tw) as session:
            async with session.get(api_url) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        if payload.get("code") != 0 or not payload.get("data"):
            raise ValueError("TikTok: cannot parse video url")

        data = payload["data"]
        video_url: Optional[str] = data.get("hdplay") or data.get("wmplay") or data.get("play")
        audio_url: Optional[str] = data.get("music")
        title: str = data.get("title") or "tiktok_video"
        duration: int = int(data.get("duration") or 0)
        cover: Optional[str] = data.get("cover") or data.get("origin_cover") or None
        author: str = "tiktok"
        author_obj = data.get("author")
        if isinstance(author_obj, dict):
            author = author_obj.get("unique_id") or author_obj.get("nickname") or author
        elif isinstance(author_obj, str) and author_obj:
            author = author_obj

        # Resolve sizes if possible (HEAD). If not, keep 0; UI can still show formats
        video_size = 0
        audio_size = 0
        async with aiohttp.ClientSession(headers={"User-Agent": TIKTOK_HEADERS["User-Agent"]}) as hs:
            if video_url:
                try:
                    async with hs.head(video_url, allow_redirects=True) as h:
                        if h.status < 400 and h.headers.get("Content-Length"):
                            video_size = int(h.headers["Content-Length"])
                except Exception:
                    pass
            if audio_url:
                try:
                    async with hs.head(audio_url, allow_redirects=True) as ah:
                        if ah.status < 400 and ah.headers.get("Content-Length"):
                            audio_size = int(ah.headers["Content-Length"])
                except Exception:
                    pass
            if not audio_size and duration:
                audio_size = int((128000 / 8) * duration)

        preview_url = None
        if cover:
            try:
                preview_url = await save_preview_on_s3(cover, title, author)
            except Exception:
                preview_url = cover

        formats = [
            SVideoFormat(quality="MP4", video_format_id="video", audio_format_id="audio", filesize=video_size),
            SVideoFormat(quality="Audio only", video_format_id="", audio_format_id="audio", filesize=audio_size),
        ]

        return SVideoResponse(
            url=self.url,
            title=title,
            author=author,
            preview_url=preview_url,
            duration=duration,
            formats=formats,
        )

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        headers_tw = {
            **TIKTOK_HEADERS,
            "Referer": "https://www.tikwm.com/",
            "Accept": "application/json, text/plain, */*",
        }
        api_url = f"https://www.tikwm.com/api/?url={download_video.url}&hd=1"

        try:
            # Resolve URLs
            async with aiohttp.ClientSession(headers=headers_tw) as session:
                async with session.get(api_url) as resp:
                    resp.raise_for_status()
                    payload = await resp.json()
            if payload.get("code") != 0 or not payload.get("data"):
                raise ValueError("TikTok: cannot resolve media urls")

            data = payload["data"]
            video_url: Optional[str] = data.get("hdplay") or data.get("wmplay") or data.get("play")
            audio_url: Optional[str] = data.get("music")
            title: str = data.get("title") or "tiktok_video"
            author = "tiktok"
            author_obj = data.get("author")
            if isinstance(author_obj, dict):
                author = author_obj.get("unique_id") or author_obj.get("nickname") or author
            elif isinstance(author_obj, str) and author_obj:
                author = author_obj

            is_audio_only = not download_video.video_format_id
            extension = ".mp3" if is_audio_only else ".mp4"
            out_dir = Path(settings.DOWNLOAD_FOLDER) / remove_all_spec_chars(author)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{task_id}_{remove_all_spec_chars(title)}{extension}"

            # choose source
            source_url = audio_url if is_audio_only and audio_url else video_url
            if not source_url:
                raise ValueError("TikTok: no suitable media stream")

            temp_path = out_path
            if is_audio_only and audio_url is None:
                temp_path = out_path.with_suffix(".temp")

            task.video_status.description = "Downloading audio track" if is_audio_only else "Downloading video track"
            await redis_cache.set_download_task(task_id, task)

            async with aiohttp.ClientSession(headers={"User-Agent": TIKTOK_HEADERS["User-Agent"]}) as dl_sess:
                async with dl_sess.get(source_url) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("Content-Length", 0))
                    read = 0
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in r.content.iter_chunked(1024 * 64):
                            if not chunk:
                                break
                            await f.write(chunk)
                            read += len(chunk)
                            if total:
                                task.video_status.percent = int(read / total * 100)
                                await redis_cache.set_download_task(task_id, task)

            # Convert to MP3 if needed
            if is_audio_only and audio_url is None:
                task.video_status.description = "Converting to MP3"
                await redis_cache.set_download_task(task_id, task)
                await convert_to_mp3(temp_path.as_posix(), out_path.as_posix())
                temp_path.unlink(missing_ok=True)

            task.filepath = out_path

            post_process = PostPrecess(task, download_video)
            await post_process.process()

            task.video_status.status = VideoDownloadStatus.COMPLETED
            task.video_status.description = VideoDownloadStatus.COMPLETED
            await redis_cache.set_download_task(task_id, task)

        except Exception as e:
            task.video_status.status = VideoDownloadStatus.ERROR
            task.video_status.description = str(e)
            await redis_cache.set_download_task(task_id, task)


