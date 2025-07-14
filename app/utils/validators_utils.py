from functools import wraps

from fastapi import HTTPException
from starlette import status

from app.routers.service import DOWNLOAD_TASKS


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