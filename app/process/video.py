import asyncio
from logging import getLogger
from pathlib import Path

from pytubefix import YouTube, Stream, StreamQuery

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DOWNLOAD_TASKS, DownloadTask
from app.schemas.main import SVideoDownload, SVideoResponse
from app.utils.helpers import get_formats, combine_audio_and_video

LOG = getLogger()


def get_audio_stream(streams: StreamQuery) -> Stream:
    main_stream = next(
        (s for s in streams if s.includes_audio_track and s.includes_video_track),
        None
    ) or streams.filter(only_audio=True).order_by('abr').first()
    return main_stream


async def get_available_formats(url):
    yt = YouTube(url)
    streams = await asyncio.to_thread(lambda: yt.streams.fmt_streams)
    audio = await asyncio.to_thread(get_audio_stream, streams)

    available_formats = await asyncio.to_thread(get_formats, streams, audio)

    return SVideoResponse(
        url=url,
        title=yt.title,
        preview_url=yt.thumbnail_url,
        formats=available_formats,
    )


async def download_video_task(task_id: str, download_video: SVideoDownload):
    task: DownloadTask = DOWNLOAD_TASKS[task_id]
    yt = YouTube(download_video.url)
    download_path = Path(settings.DOWNLOAD_FOLDER) / yt.author

    def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
        bytes_received = stream_.filesize - bytes_remaining
        percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
        task.video_status.percent = float(percent)

    yt.register_on_progress_callback(post_process_hook)
    try:
        video_path = Path(await asyncio.to_thread(
            yt.streams.get_by_itag(download_video.video_format_id).download,
            output_path=download_path.as_posix(),
            filename_prefix="video_"
        ))
        audio_path = Path(await asyncio.to_thread(
            yt.streams.get_by_itag(download_video.audio_format_id).download,
            output_path=download_path.as_posix(),
            filename_prefix="audio_"
        ))
        out_path = video_path.with_name(video_path.stem + "_out.mp4")
        await asyncio.to_thread(combine_audio_and_video,
                                video_path.as_posix(),
                                audio_path.as_posix(),
                                out_path.as_posix()
                                )
        audio_path.unlink(missing_ok=True)
        video_path.unlink(missing_ok=True)
        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.filepath = out_path

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
