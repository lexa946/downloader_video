import json
import asyncio
import aiofiles
from pathlib import Path

import aiohttp
from dataclasses import dataclass
from bs4 import BeautifulSoup

from app.config import settings
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
        # Use a separate header set when requesting media assets (add Referer)
        self._asset_headers = dict(self.headers)
        self._asset_headers["Referer"] = self.url

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, headers=self.headers) as response:
                response.raise_for_status()
                response_text = await response.text()

            video = self._parse_video_attributes(response_text)
            download_path = Path(settings.DOWNLOAD_FOLDER) / video.author / f"{task_id}_video_{video.title}"
            download_path.parent.mkdir(parents=True, exist_ok=True)

            is_audio_only = not download_video.video_format_id

            task.video_status.description = "Downloading video track" if not is_audio_only else "Downloading audio track"
            await redis_cache.set_download_task(task_id, task)
            async with session.get(video.content_url, headers=self._asset_headers) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('Content-Length', 0))
                bytes_read = 0
                temp_path = download_path

                if is_audio_only:
                    temp_path = download_path.with_suffix('.temp')

                async with aiofiles.open(temp_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)  # читаем по 8 КБ
                        if not chunk:
                            break
                        await f.write(chunk)
                        bytes_read += len(chunk)
                        task.video_status.percent = int((bytes_read / total_size) * 100)
                        await redis_cache.set_download_task(task_id, task)

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

        # Attempt to parse via embedded JSON first
        if selected is not None:
            try:
                json_ = json.loads(selected.text)
                video = InstagramVideo.from_json(json_)
                if shortcode:
                    video.title = f"video_by_{video.author}_{shortcode}.mp4"
                return video
            except Exception:
                pass

        # Fallback to OpenGraph meta tags (no cookies)
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
            raise ValueError("Unable to find media info JSON or og:video meta")

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

        video = self._parse_video_attributes(response_text)

        # Try to obtain filesize via HEAD if not parsed
        if not video.size:
            try:
                async with aiohttp.ClientSession() as session2:
                    async with session2.head(video.content_url, headers=self._asset_headers) as head_resp:
                        clen = head_resp.headers.get('Content-Length') or head_resp.headers.get('content-length')
                        if clen:
                            video.size = int(clen)
            except Exception:
                pass

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
