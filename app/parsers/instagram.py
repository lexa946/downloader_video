import asyncio
import platform
from pathlib import Path

import yt_dlp

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DOWNLOAD_TASKS, DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoFormatsResponse, SVideoDownload, SVideo
from app.utils.video_utils import save_preview_on_s3


class InstagramParser(BaseParser):
    ydl_opt = {
        'nocheckcertificate': True,
        'concurrent_fragments': 16,
        'cookiefile': 'cookie.txt',
        'quiet': True,

    }

    def __init__(self, url):
        self.url = url


    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = DOWNLOAD_TASKS[task_id]

        ydl_opts = dict(**self.ydl_opt)
        ydl_opts['format'] = "best[ext=mp4]"

        def post_process_hook(d):
            task.video_status.percent = float(d['_percent_str'].strip(" %"))

        ydl_opts['progress_hooks'] = [post_process_hook]

        if platform.system() == 'Windows':
            ydl_opts['ffmpeg_location'] = settings.FFMPEG_PATH

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            task.video_status.description = "Downloading video track"

            ydl_opts['outtmpl'] = {
                'default': f"{settings.DOWNLOAD_FOLDER}/%(uploader)s/{task_id}_video_%(title)s.%(ext)s",
            }

            info = await asyncio.to_thread(ydl.extract_info,
                                           download_video.url, download=True)
            video_path = Path(ydl.prepare_filename(info))


        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        task.filepath = video_path


    @staticmethod
    def _format_filter(format_: dict):
        return format_['abr'] is None



    @staticmethod
    def _get_audio_format(formats: list[dict]) -> dict:
        main_stream = next(
            (format_ for format_ in formats if format_['resolution']=='audio only'),
            {'format_id': "0"}
        )
        return main_stream


    async def get_formats(self) -> SVideoFormatsResponse:
        def extract_info():
            ydl_opts = dict(**self.ydl_opt)
            ydl_opts['format'] = "best[ext=mp4]"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(self.url, download=False)

        info = await asyncio.to_thread(extract_info)
        audio_format = self._get_audio_format(info.get("formats", []))

        preview_url = await save_preview_on_s3(info['thumbnail'], info['title'])

        available_formats = [
            SVideo(
                **{
                    "quality": v_format['resolution'],
                    "video_format_id": str(v_format['format_id']),
                    "audio_format_id": str(audio_format['format_id']),
                    "filesize": v_format.get('filesize_approx', 0),
                }
            ) for v_format in filter(self._format_filter, info.get("formats", []))
        ][-1:]
        return SVideoFormatsResponse(
            url=self.url,
            title=info['title'],
            preview_url=preview_url,
            duratin=int(info['duration']),
            formats=available_formats,
        )

