import asyncio
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
from app.utils.video_utils import convert_to_mp3


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
    VKVIDEO_INFO_URL = "https://vkvideo.ru/al_video.php?act=show"

    def __init__(self, url):
        self.url = url
        self.is_vk_com = "vk.com" in url
        self.is_vkvideo_ru = "vkvideo.ru" in url
        
        if self.is_vk_com:
            # Для vk.com: video335482664_456239334
            match = re.search(r"video(\d+_\d+)", url)
            if not match:
                raise ValueError("Неверный формат URL VK видео")
            self.owner_id, self.video_id = match.group(1).split("_")
        elif self.is_vkvideo_ru:
            # Для vkvideo.ru: video-212496568_456248024
            match = re.search(r"video-(\d+_\d+)", url)
            if not match:
                raise ValueError("Неверный формат URL VKVideo")
            self.owner_id, self.video_id = match.group(1).split("_")
        else:
            raise ValueError("Неподдерживаемый URL. Поддерживаются только vk.com и vkvideo.ru")
        
        self.access_token = None
        self.bytes_read = 0
        self.total_size = 0
        self.video_hash = None
        self.video_title = None

        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }
        
        if self.is_vkvideo_ru:
            self._headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://vkvideo.ru/video-{self.owner_id}_{self.video_id}",
            })
        
        self._lock = asyncio.Lock()

        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    def _extract_video_hash(self, html: str) -> str:
        """Извлекает hash видео из HTML страницы"""
        hash_match = re.search(r'og:video" content="[^"]*hash=([^&"]+)', html)
        if hash_match:
            return hash_match.group(1)
        return None

    def _extract_video_title(self, html: str) -> str:
        """Извлекает название видео из HTML страницы"""
        title_match = re.search(r'og:title" content="([^"]+)"', html)
        if title_match:
            title = title_match.group(1)
            # Очищаем название от недопустимых символов для имени файла
            return self._sanitize_filename(title)
        return None

    def _sanitize_filename(self, filename: str) -> str:
        """Очищает название файла от недопустимых символов"""
        # Удаляем или заменяем недопустимые символы
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Заменяем множественные пробелы на один
        filename = re.sub(r'\s+', ' ', filename)
        # Убираем пробелы в начале и конце
        filename = filename.strip()
        # Ограничиваем длину
        if len(filename) > 100:
            filename = filename[:100]
        return filename

    def _extract_video_urls(self, html: str) -> dict:
        """Извлекает URL видео из embed страницы"""
        video_urls = {}
        
        # HLS URL
        hls_match = re.search(r'"hls":"([^"]+)"', html)
        if hls_match:
            video_urls['hls'] = hls_match.group(1).replace('\\/', '/')
        
        # DASH URL
        dash_match = re.search(r'"dash_sep":"([^"]+)"', html)
        if dash_match:
            video_urls['dash'] = dash_match.group(1).replace('\\/', '/')
        
        # Прямые URL для разных качеств
        for quality in ['144', '240', '360', '480']:
            url_match = re.search(f'"url{quality}":"([^"]+)"', html)
            if url_match:
                video_urls[f'url{quality}'] = url_match.group(1).replace('\\/', '/')
        
        return video_urls

    def _select_best_quality(self, video_urls: dict) -> tuple:
        """Выбирает лучшее доступное качество"""
        preferred_qualities = ['url480', 'url360', 'url240', 'url144', 'hls', 'dash']
        
        for quality in preferred_qualities:
            if quality in video_urls:
                return video_urls[quality], quality
        
        return None, None

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

    async def _get_vkvideo_info(self, session: aiohttp.ClientSession) -> dict:
        """Получает информацию о видео с vkvideo.ru"""
        data = {
            "al": 1,
            "is_video_page": True,
            "video": f"-{self.owner_id}_{self.video_id}",
        }
        try:
            async with session.post(self.VKVIDEO_INFO_URL, data=data, ssl=self._ssl_context) as response:
                response.raise_for_status()
                response_json = await response.json()
            return response_json
        except Exception as e:
            print(f"VKVideo Parser Error: {e}")
            print(f"URL: {self.url}")
            print(f"Data: {data}")
            raise

    async def _get_vk_com_info(self, session: aiohttp.ClientSession) -> dict:
        """Получает информацию о видео с vk.com"""
        try:
            # 1. Получаем страницу видео для извлечения hash и названия
            print(f"1. Получаем страницу видео: {self.url}")
            async with session.get(self.url, ssl=self._ssl_context) as response:
                html = await response.text()
            
            # 2. Извлекаем hash и название
            self.video_hash = self._extract_video_hash(html)
            self.video_title = self._extract_video_title(html)
            
            if self.video_hash:
                print(f"2. Найден hash: {self.video_hash}")
            else:
                print("2. Hash не найден, пробуем без hash")
            
            if self.video_title:
                print(f"3. Название видео: {self.video_title}")
            else:
                print("3. Название видео не найдено")
                self.video_title = f"video_{self.owner_id}_{self.video_id}"
            
            # 3. Получаем embed страницу
            if self.video_hash:
                embed_url = f"https://vk.com/video_ext.php?oid={self.owner_id}&id={self.video_id}&hash={self.video_hash}"
            else:
                embed_url = f"https://vk.com/video_ext.php?oid={self.owner_id}&id={self.video_id}"
            
            print(f"4. Получаем embed страницу: {embed_url}")
            
            embed_headers = self._headers.copy()
            embed_headers.update({
                "Referer": self.url,
                "Origin": "https://vk.com"
            })
            
            async with session.get(embed_url, headers=embed_headers, ssl=self._ssl_context) as response:
                embed_html = await response.text()
                print(f"5. Embed ответ получен, размер: {len(embed_html)} байт")
            
            # 4. Извлекаем URL видео
            video_urls = self._extract_video_urls(embed_html)
            print(f"6. Найдено URL видео: {list(video_urls.keys())}")
            
            if not video_urls:
                raise Exception("URL видео не найдены")
            
            # 5. Выбираем лучшее качество
            download_url, quality_name = self._select_best_quality(video_urls)
            if not download_url:
                raise Exception("Подходящий URL видео не найден")
            
            # Формируем структуру, совместимую с VkVideo
            quality_suffix = quality_name.replace('url', '') if quality_name.startswith('url') else quality_name
            
            return {
                'title': self.video_title,
                'author': 'VK User',
                'content_urls': {quality_suffix: download_url},
                'preview_url': '',
                'duration': 0,
                'size': 0
            }
            
        except Exception as e:
            print(f"VK.com Parser Error: {e}")
            print(f"URL: {self.url}")
            raise

    async def _get_video_info(self, session: aiohttp.ClientSession) -> dict:
        """Получает информацию о видео в зависимости от типа URL"""
        if self.is_vkvideo_ru:
            return await self._get_vkvideo_info(session)
        elif self.is_vk_com:
            return await self._get_vk_com_info(session)
        else:
            raise ValueError("Неподдерживаемый тип URL")

    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        async with aiohttp.ClientSession(headers=self._headers, connector=aiohttp.TCPConnector(ssl=self._ssl_context)) as session:
            response_json = await self._get_video_info(session)
            
            # Создаем объект VkVideo из полученных данных
            if self.is_vk_com:
                # Для vk.com используем прямую структуру
                video = VkVideo(
                    title=response_json['title'],
                    author=response_json['author'],
                    content_urls=response_json['content_urls'],
                    preview_url=response_json['preview_url'],
                    duration=response_json['duration'],
                    size=response_json['size']
                )
            else:
                # Для vkvideo.ru используем существующий парсер
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

            content_url = video.content_urls[download_video.audio_format_id]

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

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task_id, task)

    async def get_formats(self) -> SVideoResponse:
        try:
            print(f"VK Parser: Starting get_formats for URL: {self.url}")
            print(f"VK Parser: owner_id={self.owner_id}, video_id={self.video_id}")
            print(f"VK Parser: is_vk_com={self.is_vk_com}, is_vkvideo_ru={self.is_vkvideo_ru}")
            
            async with aiohttp.ClientSession(headers=self._headers, connector=aiohttp.TCPConnector(ssl=self._ssl_context)) as session:
                response_json = await self._get_video_info(session)
                
            print(f"VK Parser: Got response JSON keys: {list(response_json.keys()) if isinstance(response_json, dict) else 'Not a dict'}")
            
            # Создаем объект VkVideo из полученных данных
            if self.is_vk_com:
                # Для vk.com используем прямую структуру
                video = VkVideo(
                    title=response_json['title'],
                    author=response_json['author'],
                    content_urls=response_json['content_urls'],
                    preview_url=response_json['preview_url'],
                    duration=response_json['duration'],
                    size=response_json['size']
                )
            else:
                # Для vkvideo.ru используем существующий парсер
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
