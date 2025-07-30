import uuid
from typing import Annotated

from fastapi import APIRouter, Path, HTTPException

from app.models.storage import USER_TASKS, DOWNLOAD_TASKS
from app.schemas.user import SUserHistory

router = APIRouter(prefix="/user", tags=["User"])

@router.get("/{user_id}/history")
async def get_user_history(user_id: Annotated[str, Path()]) -> SUserHistory:
    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    history_deque = USER_TASKS[user_id]
    history = SUserHistory.model_validate({
        "history": [DOWNLOAD_TASKS[task_id].video_status for task_id in history_deque],
    })
    return history
