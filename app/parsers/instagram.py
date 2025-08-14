import json
import asyncio
import aiofiles
from pathlib import Path

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
    def from_json(cls, json_: dict):
        items = json_['require'][0][3][0]['__bbox']['require'][0][3][1]['__bbox']['result']['data'][
            'xdt_api__v1__media__shortcode__web_info']['items']

        video_url = items[0]['video_versions'][0]['url']

        video_width = items[0]['video_versions'][0]['width']
        video_height = items[0]['video_versions'][0]['height']
        video_quality = f"{video_width}x{video_height}"

        video_preview_url = items[0]['image_versions2']['candidates'][0]['url']
        video_author = items[0]['user']['username']
        video_title = f"video_by_{video_author}.mp4"

        manifest_soup = BeautifulSoup(items[0]['video_dash_manifest'], features="xml")
        video_duration = int(float(manifest_soup.select_one("Period").attrs['duration'][2:-1]))

        video_size = int(
            manifest_soup.select_one("AdaptationSet[contentType='video'] Representation").attrs['FBContentLength'])
        audio_size = int(
            manifest_soup.select_one("AdaptationSet[contentType='audio'] Representation").attrs['FBContentLength'])
        full_size = video_size + audio_size

        return cls(video_title, video_url, video_preview_url, video_duration, video_quality, full_size, video_author)


class InstagramParser(BaseParser):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
    }
    cookies = {
        "csrftoken": settings.INSTAGRAM_CSRFTOKEN,
        "sessionid": settings.INSTAGRAM_SESSIONID,
    }

    def __init__(self, url):
        self.url = url
        self._response_text = None

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers, cookies=self.cookies) as response:
                response.raise_for_status()
                response_text = await response.text()

            video = self._parse_video_attributes(response_text)
            download_path = Path(settings.DOWNLOAD_FOLDER) / video.author / f"{task_id}_video_{video.title}"
            download_path.parent.mkdir(parents=True, exist_ok=True)

            is_audio_only = not download_video.video_format_id
            async with session.get(video.content_url, headers=self.headers, cookies=self.cookies) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('Content-Length', 0))
                bytes_read = 0
                temp_path = download_path

                if is_audio_only:
                    temp_path = download_path.with_suffix('.temp')

                task.filepath = temp_path
                task.video_status.description = "Downloading video track" if not is_audio_only else "Downloading audio track"
                await redis_cache.set_download_task(task_id, task)

                async with aiofiles.open(temp_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)  # читаем по 8 КБ
                        if not chunk:
                            break
                        await f.write(chunk)
                        bytes_read += len(chunk)
                        task.video_status.percent = int((bytes_read / total_size) * 100)
                        await redis_cache.set_download_task(task_id, task)
                        if await redis_cache.is_task_canceled(task_id):
                            raise DownloadUserCanceledException()

                if is_audio_only:
                    task.video_status.description = "Converting to MP3"
                    await redis_cache.set_download_task(task_id, task)
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
        await redis_cache.set_download_task(task_id, task)

    @staticmethod
    def _parse_video_attributes(content: str) -> InstagramVideo:
        soup = BeautifulSoup(content, features="lxml")

        # Try to use canonical/og:url to extract current shortcode for disambiguation
        canonical_tag = soup.select_one("link[rel='canonical']")
        if canonical_tag and canonical_tag.get("href"):
            canonical_url = canonical_tag.get("href", "")
        else:
            og_url_tag = soup.select_one("meta[property='og:url']")
            canonical_url = og_url_tag.get("content", "") if og_url_tag and og_url_tag.get("content") else ""

        shortcode = None
        if canonical_url:
            parts = [p for p in canonical_url.split('/') if p]
            for i, p in enumerate(parts):
                if p in ("reel", "reels", "p"):
                    if i + 1 < len(parts):
                        shortcode = parts[i + 1]
                    break

        # Prefer the JSON blob that contains the shortcode web info and matches the shortcode if available
        scripts = soup.select("script[type='application/json']")
        selected = None
        for tag in scripts:
            txt = tag.text
            if '"xdt_api__v1__media__shortcode__web_info"' in txt:
                if shortcode and shortcode in txt:
                    selected = tag
                    break
                if selected is None:
                    selected = tag

        if selected is None:
            # Fallback to previous heuristic
            selected = next((t for t in scripts if ".mp4" in t.text), None)
        if selected is None:
            raise ValueError("Unable to find media info JSON")

        json_ = json.loads(selected.text)
        video = InstagramVideo.from_json(json_)
        # Make title unique to avoid collisions (also fixes preview key uniqueness)
        if shortcode:
            video.title = f"video_by_{video.author}_{shortcode}.mp4"
        return video

    async def get_formats(self) -> SVideoResponse:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers, cookies=self.cookies) as response:
                response.raise_for_status()
                response_text = await response.text()

        video = self._parse_video_attributes(response_text)

        preview_url = await save_preview_on_s3(video.preview_url, video.title,  video.author)

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
