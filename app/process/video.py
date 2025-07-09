import asyncio
from logging import getLogger
from pathlib import Path


from pytubefix import YouTube, Stream

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DOWNLOAD_TASKS, DownloadTask
from app.schemas.main import SVideoDownload, SVideoResponse
from app.utils.helpers import get_formats

LOG = getLogger()

async def get_available_formats(url):
    yt = YouTube(url)
    streams = await asyncio.to_thread(lambda: yt.streams.fmt_streams)
    available_formats = await asyncio.to_thread(get_formats, streams)

    return SVideoResponse(
        url=url,
        title=yt.title,
        preview_url=yt.thumbnail_url,
        formats=available_formats,
    )


async def download_video_task(task_id: str, download_video: SVideoDownload):
    task: DownloadTask = DOWNLOAD_TASKS[task_id]
    yt = YouTube(download_video.url)
    download_path = Path(settings.DOWNLOAD_FOLDER) / yt.author / (yt.title + ".mp4")

    def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
        bytes_received = stream_.filesize - bytes_remaining
        percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
        task.video_status.percent = float(percent)

    yt.register_on_progress_callback(post_process_hook)
    try:
        new_filename = await asyncio.to_thread(yt.streams.get_by_itag(download_video.video_format_id).download,
                                output_path=download_path.parent.as_posix(),
                                filename=download_path.name
                                )

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.filepath = Path(new_filename)
    except Exception as e:
        task.video_status.status = VideoDownloadStatus.ERROR
        task.video_status.description = str(e)


async def stream_file(file_path: Path, chunk_size: int = 1024 * 1024):
    try:
        with file_path.open("rb") as file:
            while chunk := file.read(chunk_size):
                yield chunk
    finally:
        await asyncio.sleep(1)
        file_path.unlink()
        LOG.info(f"Файл {file_path} удален.")
