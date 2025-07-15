import asyncio
from datetime import timedelta
from pathlib import Path

from pytubefix import Stream, YouTube, StreamQuery

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DOWNLOAD_TASKS, DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideo, SVideoFormatsResponse, SVideoDownload
from app.utils.video_utils import save_preview_on_s3, combine_audio_and_video


class YouTubeParser(BaseParser):

    def __init__(self, url):
        self.url = url
        self._yt = YouTube(self.url)

    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = DOWNLOAD_TASKS[task_id]

        download_path = Path(settings.DOWNLOAD_FOLDER) / self._yt.author

        def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
            bytes_received = stream_.filesize - bytes_remaining
            percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
            task.video_status.percent = float(percent)

        self._yt.register_on_progress_callback(post_process_hook)
        try:
            task.video_status.description = "Downloading video track"

            video_path = Path(await asyncio.to_thread(
                self._yt.streams.get_by_itag(download_video.video_format_id).download,
                output_path=download_path.as_posix(),
                filename_prefix=f"{task_id}_video_"
            ))

            task.video_status.description = "Downloading audio track"
            audio_path = Path(await asyncio.to_thread(
                self._yt.streams.get_by_itag(download_video.audio_format_id).download,
                output_path=download_path.as_posix(),
                filename_prefix=f"{task_id}_audio_"
            ))
            task.video_status.description = "Merging tracks"
            out_path = video_path.with_name(video_path.stem + "_out.mp4")
            await asyncio.to_thread(combine_audio_and_video,
                                    video_path.as_posix(),
                                    audio_path.as_posix(),
                                    out_path.as_posix()
                                    )
            audio_path.unlink(missing_ok=True)
            video_path.unlink(missing_ok=True)
            task.video_status.status = VideoDownloadStatus.COMPLETED
            task.video_status.description = VideoDownloadStatus.COMPLETED
            task.filepath = out_path

        except Exception as e:
            task.video_status.status = VideoDownloadStatus.ERROR
            task.video_status.description = str(e)


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


    async def get_formats(self) -> SVideoFormatsResponse:
        streams = await asyncio.to_thread(lambda: self._yt.streams.fmt_streams)
        audio = await asyncio.to_thread(self._get_audio_stream, streams)

        preview_url = await save_preview_on_s3(self._yt.thumbnail_url, self._yt.title)
        duration = timedelta(milliseconds=int(audio.durationMs)).seconds
        available_formats = [
            SVideo(
                **{
                    "quality": v_format.resolution,
                    "video_format_id": str(v_format.itag),
                    "audio_format_id": str(audio.itag),
                    "filesize": round(v_format.filesize + audio.filesize, 2),
                }
            ) for v_format in filter(self._format_filter, streams)
        ]
        return SVideoFormatsResponse(
            url=self.url,
            title=self._yt.title,
            preview_url=preview_url,
            duration=duration,
            formats=available_formats,
        )