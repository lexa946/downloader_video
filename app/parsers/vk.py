import asyncio
import re
import aiofiles
from pathlib import Path

import aiohttp
from dataclasses import dataclass

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DOWNLOAD_TASKS, DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoFormatsResponse, SVideoDownload, SVideo
from app.utils.helpers import remove_all_spec_chars


@dataclass
class VkVideo:
    title: str
    author: str
    content_urls: dict[str, str]
    preview_url: str
    duration: int
    size: int

    @classmethod
    def from_json(cls, json_: dict):
        video_info = json_['payload'][1][4]['player']['params'][0]
        video_title = video_info['md_title']
        video_author = video_info['md_author']
        content_urls = {
            str(quality): video_info[f"url{quality}"] for quality in (144, 240, 360, 480, 720, 1080)
            if f"url{quality}" in video_info
        }
        video_preview_url = video_info['jpg']
        video_duration = video_info['duration']
        size = 0
        return cls(video_title, video_author, content_urls, video_preview_url, video_duration, size)


class VkParser(BaseParser):
    CONNECTIONS_COUNT = 10
    CHUNK_SIZE = 1024 * 64
    VIDEO_INFO_URL = "https://vkvideo.ru/al_video.php?act=show"

    def __init__(self, url):

        self.url = url
        self.owner_id, self.video_id = re.search(r"video-(\d+_\d+)", self.url).group(1).split("_")
        self.access_token = None
        self.bytes_read = 0
        self.total_size = 0

        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://vkvideo.ru/video-{self.owner_id}_{self.video_id}",
        }
        self._lock = asyncio.Lock()

    async def _fetch_range(self,
                           session: aiohttp.ClientSession,
                           url: str,
                           start: int,
                           end: int,
                           part_number: int,
                           task_id: str,
                           task: DownloadTask,
                           download_path: Path,
                           ):
        headers = {
            **self._headers,
            "Range": f"bytes={start}-{end}",
        }
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()

            part_file = download_path.parent / task_id / f"part_{part_number}.tmp"
            part_file.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(part_file, "wb") as f:
                async for chunk in resp.content.iter_chunked(self.CHUNK_SIZE):
                    async with self._lock:
                        self.bytes_read += len(chunk)
                        task.video_status.percent = int((self.bytes_read / self.total_size) * 100)
                    await f.write(chunk)
        return part_file

    @staticmethod
    async def _merge_parts(part_files: list[Path], output_file: Path):
        async with aiofiles.open(output_file, "wb") as out:
            for part in part_files:
                async with aiofiles.open(part, "rb") as pf:
                    content = await pf.read()
                    await out.write(content)
                part.unlink()
            else:
                part.parent.rmdir()

    async def _get_video_info(self, session: aiohttp.ClientSession) -> dict:
        data = {
            "al": 1,
            "is_video_page": True,
            "video": f"-{self.owner_id}_{self.video_id}",
        }
        async with session.post(self.VIDEO_INFO_URL, data=data) as response:
            response.raise_for_status()
            response_json = await response.json()
        return response_json

    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = DOWNLOAD_TASKS[task_id]
        async with aiohttp.ClientSession(headers=self._headers) as session:
            response_json = await self._get_video_info(session)
            video = VkVideo.from_json(response_json)

            download_path = (
                    Path(settings.DOWNLOAD_FOLDER) /
                    remove_all_spec_chars(video.author) /
                    f"{task_id}_{remove_all_spec_chars(video.title)}.mp4"
            )
            download_path.parent.mkdir(parents=True, exist_ok=True)

            task.video_status.description = "Downloading video track"

            content_url = video.content_urls[download_video.video_format_id]

            async with session.get(content_url) as response:
                response.raise_for_status()
                self.total_size = int(response.headers.get('Content-Length', 0))

            ranges = []
            for i in range(self.CONNECTIONS_COUNT):
                start = i * (self.total_size // self.CONNECTIONS_COUNT)
                end = (
                        start + (self.total_size // self.CONNECTIONS_COUNT) - 1
                ) if i < self.CONNECTIONS_COUNT - 1 else self.total_size - 1
                ranges.append((start, end, i))

            tasks = [
                self._fetch_range(session, content_url, start, end, part_num, task_id, task, download_path)
                for start, end, part_num in ranges
            ]
            part_files = await asyncio.gather(*tasks)

            task.video_status.description = "Merging parts video track"
            await self._merge_parts(part_files, download_path)

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        task.filepath = download_path

    async def get_formats(self) -> SVideoFormatsResponse:
        async with aiohttp.ClientSession(headers=self._headers) as session:
            response_json = await self._get_video_info(session)
        video = VkVideo.from_json(response_json)

        available_formats = [
            SVideo(
                **{
                    "quality": f"{quality}p",
                    "video_format_id": quality,
                    "audio_format_id": f"",
                    "filesize": video.size,
                }
            )
            for quality, url in video.content_urls.items()
        ]
        return SVideoFormatsResponse(
            url=self.url,
            title=video.title,
            author=video.author,
            preview_url=video.preview_url,
            duration=video.duration,
            formats=available_formats,
        )
