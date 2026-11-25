import re
import time
import asyncio
import aiohttp
import json as _json
import ssl

from datetime import timedelta
from logging import getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, TypeVar
from urllib.error import URLError
from urllib.parse import quote_plus

from fastapi import HTTPException
from pytubefix import Stream, YouTube, StreamQuery
from pytubefix.exceptions import MaxRetriesExceeded, VideoUnavailable
from bs4 import BeautifulSoup

from app.config import settings
from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoFormat, SVideoResponse, SVideoDownload, SYoutubeSearchItem
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, combine_audio_and_video, convert_to_mp3


LOG = getLogger(__name__)
T = TypeVar("T")


class YouTubeConnectionError(RuntimeError):
    pass


class YouTubeParser(BaseParser):

    def __init__(self, url):
        self.url = url
        self._yt = YouTube(self.url)

    async def _with_connection_retry(self, operation: Callable[[], T], stage: str) -> T:
        for attempt in range(2):
            try:
                return await asyncio.to_thread(operation)
            except (URLError, ssl.SSLError, MaxRetriesExceeded) as exc:
                reason = exc.reason if isinstance(exc, URLError) else exc
                if not isinstance(reason, (ssl.SSLEOFError, MaxRetriesExceeded)):
                    raise
                if attempt == 1:
                    LOG.warning("YouTube connection failed while %s", stage, exc_info=True)
                    raise YouTubeConnectionError(
                        "Не удалось получить данные от YouTube. Попробуйте ещё раз."
                    ) from exc
                await asyncio.sleep(0.5)
                self._yt = YouTube(self.url)

    @classmethod
    async def search_videos(cls, query: str) -> list[SYoutubeSearchItem]:

        try:
            search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"

            async with aiohttp.ClientSession(headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru,en;q=0.9",
            }) as session:
                async with session.get(search_url) as resp:
                    resp.raise_for_status()
                    html = await resp.text()

            yt_initial_json = None
            m = re.search(r"ytInitialData\s*=\s*(\{[\s\S]*?\});", html)
            if m:
                try:
                    yt_initial_json = _json.loads(m.group(1))
                except Exception:
                    yt_initial_json = None

            search_items: list[dict] = []
            if yt_initial_json:
                # Walk through contents to find videoRenderer entries
                def walk(obj):
                    if isinstance(obj, dict):
                        if "videoRenderer" in obj:
                            search_items.append(obj["videoRenderer"])
                        for v in obj.values():
                            walk(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            walk(v)

                walk(yt_initial_json)
            else:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("a#video-title[href^='/watch']"):
                    search_items.append({
                        "navigationEndpoint": {"commandMetadata": {"webCommandMetadata": {"url": a.get("href")}}},
                        "title": {"runs": [{"text": a.get("title") or a.get_text(strip=True)}]},
                    })

            result_items: list[SYoutubeSearchItem] = []

            for item in search_items:
                url_path = (
                    item.get("navigationEndpoint", {})
                    .get("commandMetadata", {})
                    .get("webCommandMetadata", {})
                    .get("url")
                )
                if isinstance(url_path, str) and url_path.startswith("/watch"):
                    url = f"https://www.youtube.com{url_path}"
                else:
                    continue

                title = "".join(run.get("text", "") for run in item.get("title", {}).get("runs"))

                author = "".join(run.get("text", "") for run in (
                        item.get("longBylineText", {}).get("runs") or item.get("ownerText", {}).get("runs")
                ))

                thumbnail_url = None
                thumbs = item.get("thumbnail", {}).get("thumbnails", [])
                if thumbs:
                    thumbnail_url = thumbs[-1].get("url")

                duration_seconds = None
                duration_text = item.get("lengthText", {}).get("simpleText")
                if duration_text:
                    parts = duration_text.split(":")
                    secs = 0
                    for p in parts:
                        secs = secs * 60 + int(p)
                    duration_seconds = secs

                result_items.append(SYoutubeSearchItem(
                    video_url=url,
                    title=title or url,
                    author=author,
                    duration=duration_seconds,
                    thumbnail_url=thumbnail_url,
                ))

                if len(result_items) >= 6:
                    break

            return result_items
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"YouTube search failed: {e}")

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)

        download_path = Path(settings.DOWNLOAD_FOLDER) / task.video_status.video.author
        task.filepath = download_path
        event_loop = asyncio.get_running_loop()

        last_t = time.time()
        last_bytes = 0

        def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
            nonlocal last_t, last_bytes
            bytes_received = stream_.filesize - bytes_remaining
            percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
            now = time.time()
            dt = max(1e-3, now - last_t)
            speed = float(max(0.0, (bytes_received - last_bytes)) / dt)
            remain = max(0, stream_.filesize - bytes_received)
            eta = int(remain / max(1.0, speed)) if speed > 0 else None
            last_t = now
            last_bytes = bytes_received

            task.video_status.percent = float(percent)
            task.video_status.speed_bps = speed
            task.video_status.eta_seconds = eta

            async def _update_and_check():
                await redis_cache.set_download_task(task)
                if await redis_cache.is_task_canceled(task_id):
                    raise DownloadUserCanceledException()

            asyncio.run_coroutine_threadsafe(_update_and_check(), event_loop).result()

        def download_track(itag: str, track: str) -> Path:
            nonlocal last_t, last_bytes
            last_t = time.time()
            last_bytes = 0
            self._yt.register_on_progress_callback(post_process_hook)
            stream = self._yt.streams.get_by_itag(itag)
            if stream is None:
                raise ValueError(f"YouTube format {itag} is no longer available.")

            download_path.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=download_path) as staging:
                filename = stream.download(
                    output_path=staging,
                    filename_prefix=f"{task_id}_{track}_",
                    timeout=30,
                    max_retries=2,
                )
                if not filename:
                    raise RuntimeError(f"YouTube returned no {track} file.")
                source = Path(filename)
                if source.stat().st_size == 0:
                    raise RuntimeError(f"YouTube returned an empty {track} file.")
                return source.replace(download_path / source.name)

        if not download_video.video_format_id:
            task.video_status.description = "Downloading audio track"
            await redis_cache.set_download_task(task)
            audio_path = await self._with_connection_retry(
                lambda: download_track(download_video.audio_format_id, "audio"), "downloading audio"
            )

            task.video_status.description = "Converting to MP3"
            await redis_cache.set_download_task(task)
            out_path = audio_path.with_suffix('.mp3')
            await asyncio.to_thread(convert_to_mp3,
                                    audio_path.as_posix(),
                                    out_path.as_posix()
                                    )
            audio_path.unlink(missing_ok=True)
            task.filepath = out_path

        else:
            # Стандартная логика для видео
            task.video_status.description = "Downloading video track"
            await redis_cache.set_download_task(task)
            video_path = await self._with_connection_retry(
                lambda: download_track(download_video.video_format_id, "video"), "downloading video"
            )
            if download_video.audio_format_id != download_video.video_format_id:
                task.video_status.description = "Downloading audio track"
                await redis_cache.set_download_task(task)
                try:
                    audio_path = await self._with_connection_retry(
                        lambda: download_track(download_video.audio_format_id, "audio"), "downloading audio"
                    )
                except YouTubeConnectionError:
                    video_path.unlink(missing_ok=True)
                    raise
                task.video_status.description = "Merging tracks"
                await redis_cache.set_download_task(task)
                out_path = video_path.with_name(video_path.stem + "_out.mp4")
                await asyncio.to_thread(combine_audio_and_video,
                                        video_path.as_posix(),
                                        audio_path.as_posix(),
                                        out_path.as_posix()
                                        )
                audio_path.unlink(missing_ok=True)
                video_path.unlink(missing_ok=True)
                video_path = out_path
            task.filepath = video_path

        post_process = PostPrecess(task, download_video)
        await post_process.process()

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task)

    @staticmethod
    def _format_filter(stream: Stream):
        return (
                stream.type == "video" and
                stream.video_codec.startswith("avc1") and
                stream.height >= settings.MIN_VIDEO_HEIGHT
        )

    @staticmethod
    def _get_audio_stream(streams: StreamQuery) -> Stream | None:
        main_stream = next(
            (s for s in streams if s.includes_audio_track and s.includes_video_track),
            None
        ) or streams.filter(only_audio=True).order_by('abr').first()
        return main_stream

    async def get_formats(self) -> SVideoResponse:
        try:
            video = await self._with_connection_retry(self._read_formats, "reading video formats")
        except YouTubeConnectionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except VideoUnavailable as exc:
            raise HTTPException(404, "Видео недоступно на YouTube.") from exc

        if video.preview_url:
            video.preview_url = await save_preview_on_s3(video.preview_url, video.title, video.author)
        return video

    def _read_formats(self) -> SVideoResponse:
        streams = self._yt.streams
        audio = self._get_audio_stream(streams)
        if audio is None:
            raise HTTPException(status_code=404, detail="У этого видео нет доступной аудиодорожки.")
        duration = timedelta(milliseconds=int(audio.durationMs)).seconds

        # Get video formats
        available_formats = [
            SVideoFormat(
                **{
                    "quality": v_format.resolution,
                    "video_format_id": str(v_format.itag),
                    "audio_format_id": str(audio.itag),
                    "filesize": round(v_format.filesize + audio.filesize, 2),
                }
            ) for v_format in filter(self._format_filter, streams)
        ]

        # Add audio-only format
        if not available_formats:
            fallback = streams.filter(progressive=True, file_extension="mp4").order_by("resolution").last()
            if fallback:
                available_formats.append(SVideoFormat(
                    quality=fallback.resolution, video_format_id=str(fallback.itag),
                    audio_format_id=str(fallback.itag), filesize=fallback.filesize,
                ))
        audio_format = SVideoFormat(
            quality="Audio only",
            video_format_id="",
            audio_format_id=str(audio.itag),
            filesize=round(audio.filesize, 2)
        )
        available_formats.append(audio_format)

        return SVideoResponse(
            url=self.url,
            title=self._yt.title,
            preview_url=self._yt.thumbnail_url,
            duration=duration,
            formats=available_formats,
            author=self._yt.author,
        )
