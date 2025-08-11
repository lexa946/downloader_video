from functools import wraps
import inspect

from fastapi import HTTPException
from starlette import status

from app.models.cache import redis_cache


def check_task_id(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            bound = inspect.signature(func).bind_partial(*args, **kwargs)
            task_id = bound.arguments.get("task_id")
        except Exception:
            task_id = kwargs.get("task_id")
            if task_id is None and args:
                # На случай если task_id передан позиционно первым
                task_id = args[0]

        is_exists = await redis_cache.exist_download_task(task_id)
        if not is_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found."
            )
        return await func(*args, **kwargs)
    return wrapper