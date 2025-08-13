import asyncio
import json
import re
import ssl
import aiofiles
from pathlib import Path

import aiohttp
from dataclasses import dataclass

from app.config import settings
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoResponse, SVideoDownload, SVideoFormat
from app.utils.helpers import remove_all_spec_chars
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import convert_to_mp3, cut_media


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
        try:
            # Разные возможные структуры ответа от VK API
            if 'payload' in json_ and len(json_['payload']) > 1:
                video_info = json_['payload'][1][4]['player']['params'][0]
            elif "params" in json_:
                video_info = json_['params'][0]
            else:
                # Альтернативная структура
                video_info = json_
                
            video_title = video_info.get('md_title', 'Без названия')
            video_author = video_info.get('md_author', 'Неизвестный автор')
            
            # Ищем доступные качества видео
            content_urls = {}
            for quality in (144, 240, 360, 480, 720, 1080):
                url_key = f"url{quality}"
                if url_key in video_info and video_info[url_key]:
                    content_urls[str(quality)] = video_info[url_key]
            
            video_preview_url = video_info.get('jpg', '')
            video_duration = video_info.get('duration', 0)
            size = 0
            
            return cls(video_title, video_author, content_urls, video_preview_url, video_duration, size)
        except Exception as e:
            print(f"Error parsing VK video info: {e}")
            print(f"JSON structure: {json_}")
            raise ValueError(f"Cannot parse VK video info: {e}")


class VkParser(BaseParser):
    CONNECTIONS_COUNT = 10
    CHUNK_SIZE = 1024 * 64
    VIDEO_INFO_URL = "https://vkvideo.ru/al_video.php?act=show"

    def __init__(self, url):

        self.url = url
        self.owner_id, self.video_id = re.search(r"video-?(\d+_\d+)", self.url).group(1).split("_")
        self.access_token = None
        self.bytes_read = 0
        self.total_size = 0

        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://vkvideo.ru/video-{self.owner_id}_{self.video_id}",
        }
        self._lock = asyncio.Lock()

        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

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
        async with session.get(url, headers=headers, ssl=self._ssl_context) as resp:
            resp.raise_for_status()

            part_file = download_path.parent / task_id / f"part_{part_number}.tmp"
            part_file.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(part_file, "wb") as f:
                async for chunk in resp.content.iter_chunked(self.CHUNK_SIZE):
                    async with self._lock:
                        self.bytes_read += len(chunk)
                        task.video_status.percent = int((self.bytes_read / self.total_size) * 100)
                        await redis_cache.set_download_task(task_id, task)  # Update task in Redis
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
        try:
            if "vkvideo" in self.url:
                data = {
                    "al": 1,
                    "is_video_page": True,
                    "video": f"-{self.owner_id}_{self.video_id}",
                }
                async with session.post(self.VIDEO_INFO_URL, data=data, ssl=self._ssl_context) as response:
                    response.raise_for_status()
                    response_json = await response.json()
                return response_json
            else:
                embed_url = f"https://vk.com/video_ext.php?oid={self.owner_id}&id={self.video_id}"
                async with session.get(embed_url,  ssl=self._ssl_context) as response:
                    response.raise_for_status()
                    html = await response.text()
                    json_str = re.search(r'var\s+playerParams\s*=\s*(\{[\s\S]*?\});', html).group(1)
                    response_json = json.loads(json_str)
                    return response_json
        except Exception as e:
            print(f"VK Parser Error: {e}")
            print(f"URL: {self.url}")
            raise

    # @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        async with aiohttp.ClientSession(headers=self._headers, connector=aiohttp.TCPConnector(ssl=self._ssl_context)) as session:
            response_json = await self._get_video_info(session)
            video = VkVideo.from_json(response_json)

            is_audio_only = not download_video.video_format_id
            extension = '.mp3' if is_audio_only else '.mp4'

            download_path = (
                    Path(settings.DOWNLOAD_FOLDER) /
                    remove_all_spec_chars(video.author) /
                    f"{task_id}_{remove_all_spec_chars(video.title)}{extension}"
            )
            temp_path = download_path.with_suffix('.temp') if is_audio_only else download_path
            download_path.parent.mkdir(parents=True, exist_ok=True)

            task.video_status.description = "Downloading audio track" if is_audio_only else "Downloading video track"
            await redis_cache.set_download_task(task_id, task)

            if is_audio_only:
                content_url = video.content_urls[download_video.audio_format_id]
            else:
                content_url = video.content_urls[download_video.video_format_id]

            async with session.get(content_url, ssl=self._ssl_context) as response:
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
                self._fetch_range(session, content_url, start, end, part_num, task_id, task, temp_path)
                for start, end, part_num in ranges
            ]
            part_files = await asyncio.gather(*tasks)

            task.video_status.description = "Merging parts"
            await redis_cache.set_download_task(task_id, task)
            await self._merge_parts(part_files, temp_path)

            if is_audio_only:
                task.video_status.description = "Converting to MP3"
                await redis_cache.set_download_task(task_id, task)
                await asyncio.to_thread(convert_to_mp3,
                                    temp_path.as_posix(),
                                    download_path.as_posix()
                                    )
                temp_path.unlink(missing_ok=True)
                task.filepath = download_path
            else:
                task.filepath = temp_path

        # Optional clipping
        if download_video.start_seconds is not None or download_video.end_seconds is not None:
            task.video_status.description = "Clipping selected fragment"
            await redis_cache.set_download_task(task_id, task)
            clipped_path = task.filepath.with_name(task.filepath.stem + "_clip" + task.filepath.suffix)
            await asyncio.to_thread(
                cut_media,
                task.filepath.as_posix(),
                clipped_path.as_posix(),
                download_video.start_seconds,
                download_video.end_seconds,
            )
            task.filepath.unlink(missing_ok=True)
            task.filepath = clipped_path

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task_id, task)

    async def get_formats(self) -> SVideoResponse:
        try:
            print(f"VK Parser: Starting get_formats for URL: {self.url}")
            print(f"VK Parser: owner_id={self.owner_id}, video_id={self.video_id}")
            
            async with aiohttp.ClientSession(headers=self._headers, connector=aiohttp.TCPConnector(ssl=self._ssl_context)) as session:
                response_json = await self._get_video_info(session)
                
            print(f"VK Parser: Got response JSON keys: {list(response_json.keys()) if isinstance(response_json, dict) else 'Not a dict'}")
            
            video = VkVideo.from_json(response_json)
            print(f"VK Parser: Parsed video - title: {video.title}, available qualities: {list(video.content_urls.keys())}")

            if not video.content_urls:
                raise ValueError("No video URLs found in VK response")

            available_formats = [
                SVideoFormat(
                    **{
                        "quality": f"{quality}p",
                        "video_format_id": quality,
                        "audio_format_id": quality,
                        "filesize": video.size,
                    }
                )
                for quality, url in video.content_urls.items()
            ]

            min_quality = min(video.content_urls.keys(), key=int)
            available_formats.append(
                SVideoFormat(
                    **{
                        "quality": "Audio only",
                        "video_format_id": "",
                        "audio_format_id": min_quality,
                        "filesize": video.size // 4,
                    }
                )
            )

            print(f"VK Parser: Created {len(available_formats)} formats")
            
            return SVideoResponse(
                url=self.url,
                title=video.title,
                author=video.author,
                preview_url=video.preview_url,
                duration=video.duration,
                formats=available_formats,
            )
        except Exception as e:
            print(f"VK Parser get_formats error: {e}")
            import traceback
            traceback.print_exc()
            raise
