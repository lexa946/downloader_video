from functools import wraps

from fastapi import HTTPException
from pytubefix import Stream
from starlette import status

from app.config import settings
from app.routers.service import DOWNLOAD_TASKS
from app.schemas.main import SVideo


def format_filter(stream: Stream):
    return (
        stream.type == "video" and
        stream.video_codec.startswith("avc1") and
        stream.height > settings.MIN_VIDEO_HEIGHT
    )


def get_formats(streams: list[Stream]):
    formats_all = list(filter(format_filter, streams))
    available_formats = [
        SVideo(
            **{
                "quality": v_format.resolution,
                "video_format_id": v_format.itag,
                "filesize": v_format.filesize_mb
            }
        ) for v_format in formats_all
    ]
    return available_formats


def check_task_id(func):
    @wraps(func)
    async def wrapper(task_id):
        if task_id not in DOWNLOAD_TASKS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found."
            )
        return await func(task_id)
    return wrapper
