from functools import wraps
import inspect
from uuid import UUID

from fastapi import HTTPException
from starlette import status

from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.schemas.main import SVideoDownload


def fallback_background_task(func):
    @wraps(func)
    async def wrapper(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        try:
            await func(self, task_id, download_video)
        except Exception as e:
            task.video_status.status = VideoDownloadStatus.ERROR
            task.video_status.description = str(e)
            await redis_cache.set_download_task(task_id, task)
    return wrapper


def check_task_id(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            task_id = bound.arguments.get("task_id")
        except Exception:
            task_id = kwargs.get("task_id")
            if task_id is None and args:
                task_id = args[0]

        if not task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="task_id is required",
            )
        try:
            UUID(str(task_id))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid task_id",
            )

        is_exists = await redis_cache.exist_download_task(task_id)
        if not is_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found."
            )
        return await func(*args, **kwargs)
    return wrapper