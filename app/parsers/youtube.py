import re
import asyncio
import aiohttp
import json as _json

from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import HTTPException
from pytubefix import Stream, YouTube, StreamQuery, Search
from bs4 import BeautifulSoup

from app.config import settings
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoFormat, SVideoResponse, SVideoDownload, SYoutubeSearchItem
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, combine_audio_and_video, convert_to_mp3

class YouTubeParser(BaseParser):

    def __init__(self, url):
        self.url = url
        self._yt = YouTube(self.url)

    @classmethod
    async def search_videos(cls, query: str) -> list[SYoutubeSearchItem]:

        def sync_search():
            result_items = []
            upload_jobs = []
            search = Search(query)
            video: YouTube
            for video in search.results:
                result_items.append(SYoutubeSearchItem(
                    video_url=video.watch_url,
                    title=video.title,
                    author=video.author,
                    duration=timedelta(milliseconds=int(video.streams.first().durationMs)).seconds,
                    thumbnail_url=video.thumbnail_url,
                ))

                if video.thumbnail_url:
                    upload_jobs.append(save_preview_on_s3(video.thumbnail_url, video.title, video.author))
            return result_items, upload_jobs

        result_items, upload_jobs = await asyncio.to_thread(sync_search)

        if upload_jobs:
            uploaded_urls = await asyncio.gather(*upload_jobs, return_exceptions=True)
            idx = 0
            for i, item in enumerate(result_items):
                if item.thumbnail_url:
                    new_url = uploaded_urls[idx]
                    idx += 1
                    if isinstance(new_url, str) and new_url:
                        item.thumbnail_url = new_url

        return result_items




    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)

        download_path = Path(settings.DOWNLOAD_FOLDER) / self._yt.author
        event_loop = asyncio.get_event_loop()

        def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
            bytes_received = stream_.filesize - bytes_remaining
            percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
            task.video_status.percent = float(percent)
            event_loop.create_task(redis_cache.set_download_task(task_id, task))

        self._yt.register_on_progress_callback(post_process_hook)
        try:
            if not download_video.video_format_id:
                task.video_status.description = "Downloading audio track"
                await redis_cache.set_download_task(task_id, task)
                audio_path = Path(await asyncio.to_thread(
                    self._yt.streams.get_by_itag(download_video.audio_format_id).download,
                    output_path=download_path.as_posix(),
                    filename_prefix=f"{task_id}_audio_"
                ))
                
                # Конвертируем в MP3
                task.video_status.description = "Converting to MP3"
                await redis_cache.set_download_task(task_id, task)
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
                await redis_cache.set_download_task(task_id, task)
                video_path = Path(await asyncio.to_thread(
                    self._yt.streams.get_by_itag(download_video.video_format_id).download,
                    output_path=download_path.as_posix(),
                    filename_prefix=f"{task_id}_video_"
                ))
                if download_video.audio_format_id != download_video.video_format_id:
                    task.video_status.description = "Downloading audio track"
                    await redis_cache.set_download_task(task_id, task)
                    audio_path = Path(await asyncio.to_thread(
                        self._yt.streams.get_by_itag(download_video.audio_format_id).download,
                        output_path=download_path.as_posix(),
                        filename_prefix=f"{task_id}_audio_"
                    ))
                    task.video_status.description = "Merging tracks"
                    await redis_cache.set_download_task(task_id, task)
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
            await redis_cache.set_download_task(task_id, task)

        except Exception as e:
            task.video_status.status = VideoDownloadStatus.ERROR
            task.video_status.description = str(e)
            await redis_cache.set_download_task(task_id, task)


    @staticmethod
    def _format_filter(stream: Stream):
        return (
            stream.type == "video" and
            stream.video_codec.startswith("avc1") and
            stream.height > settings.MIN_VIDEO_HEIGHT
        )


    @staticmethod
    def _get_audio_stream(streams: StreamQuery) -> Stream:
        main_stream = next(
            (s for s in streams if s.includes_audio_track and s.includes_video_track),
            None
        ) or streams.filter(only_audio=True).order_by('abr').first()
        return main_stream


    async def get_formats(self) -> SVideoResponse:
        streams = await asyncio.to_thread(lambda: self._yt.streams.fmt_streams)
        audio = await asyncio.to_thread(self._get_audio_stream, streams)

        preview_url = await save_preview_on_s3(self._yt.thumbnail_url,self._yt.title, self._yt.author)
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
            preview_url=preview_url,
            duration=duration,
            formats=available_formats,
            author=self._yt.author,
        )