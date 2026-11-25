import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.models.cache import redis_cache

router = APIRouter(prefix="/api/cookie-consent", tags=["Service"])
CONSENT_AGE = 365 * 24 * 60 * 60


class ConsentChoice(BaseModel):
    accepted: bool


async def has_consent(request: Request) -> bool:
    token = request.cookies.get("site_consent")
    if not token:
        return False
    try:
        uuid.UUID(token)
    except ValueError:
        return False
    return bool(await redis_cache.redis.exists(redis_cache._get_key(f"consent:{token}")))


@router.get("")
async def get_consent(request: Request):
    return {"accepted": await has_consent(request)}


@router.post("")
async def set_consent(choice: ConsentChoice, request: Request):
    old_token = request.cookies.get("site_consent")
    if old_token:
        await redis_cache.redis.delete(redis_cache._get_key(f"consent:{old_token}"))
    response = JSONResponse({"accepted": choice.accepted})
    response.delete_cookie("site_consent")
    if choice.accepted:
        token = str(uuid.uuid4())
        await redis_cache.redis.set(redis_cache._get_key(f"consent:{token}"), "1", ex=CONSENT_AGE)
        response.set_cookie("site_consent", token, max_age=CONSENT_AGE, httponly=True,
                            secure=request.url.scheme == "https", samesite="lax")
        if not request.cookies.get("user_id"):
            response.set_cookie("user_id", str(uuid.uuid4()), max_age=CONSENT_AGE,
                                httponly=True, secure=request.url.scheme == "https", samesite="lax")
    else:
        user_id = request.cookies.get("user_id")
        if user_id:
            task_id = await redis_cache.get_user_active_task(user_id)
            if task_id:
                await redis_cache.cancel_pending_task(task_id)
                await redis_cache.release_user_active_task(user_id, task_id)
        response.delete_cookie("user_id")
    return response
