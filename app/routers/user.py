import uuid
from typing import Annotated

from fastapi import APIRouter, Path, HTTPException

from app.models.cache import redis_cache
from app.schemas.user import SUserHistory

router = APIRouter(prefix="/user", tags=["User"])

@router.get("/{user_id}/history")
async def get_user_history(user_id: Annotated[str, Path()]) -> SUserHistory:
    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    history_deque = await redis_cache.get_user_tasks(user_id)
    tasks = []
    for task_id in history_deque:
        task = await redis_cache.get_download_task(task_id)
        if task is None:
            await redis_cache.delete_download_task(task_id)
            continue
        tasks.append(task.video_status)
    history = SUserHistory.model_validate({
        "history": tasks,
    })
    return history
