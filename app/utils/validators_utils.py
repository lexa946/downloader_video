from functools import wraps

from fastapi import HTTPException
from starlette import status

from app.models.cache import redis_cache


def check_task_id(func):
    @wraps(func)
    async def wrapper(task_id):
        is_exists = await redis_cache.exist_download_task(task_id)
        if not is_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found."
            )
        return await func(task_id)
    return wrapper