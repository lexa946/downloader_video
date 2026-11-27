from pathlib import Path
import asyncio
from logging import getLogger
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.routing import Match
from app.config import settings
from starlette.staticfiles import StaticFiles

from app.routers.service import router as service_router
from app.routers.consent import router as consent_router, has_consent
from app.routers.front import router as new_front_router
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.queue import task_queue

app = FastAPI(docs_url=None if settings.APP_ENV == "production" else "/docs",
              redoc_url=None if settings.APP_ENV == "production" else "/redoc",
              openapi_url=None if settings.APP_ENV == "production" else "/openapi.json")
LOG = getLogger(__name__)


async def check_media_proxy():
    proxy_url = settings.MEDIA_PROXY_URL
    if not proxy_url:
        LOG.warning("Mihomo proxy is not configured. YouTube and Instagram use direct connections.")
        return
    parsed = urlsplit(proxy_url)
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname, parsed.port or 80), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        LOG.info("Mihomo HTTP proxy is reachable at %s:%s", parsed.hostname, parsed.port or 80)
    except (OSError, asyncio.TimeoutError, ValueError) as exc:
        LOG.error("Mihomo HTTP proxy is unreachable at %s:%s: %s",
                  parsed.hostname, parsed.port or 80, exc)

@app.middleware("http")
async def require_cookie_consent(request: Request, call_next):
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/cookie-consent"):
        matches_service_route = any(
            route.matches(request.scope)[0] != Match.NONE for route in service_router.routes
        )
        if matches_service_route and not await has_consent(request):
            return JSONResponse({"detail": "Требуется согласие на использование cookie."}, status_code=403)
    return await call_next(request)

app.include_router(consent_router)
app.include_router(service_router)
app.include_router(new_front_router)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")


async def redirect_to_home(scope, receive, send):
    if scope["type"] != "http":
        await app.router.not_found(scope, receive, send)
        return
    response = RedirectResponse(url="/", status_code=303)
    await response(scope, receive, send)


app.router.default = redirect_to_home


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path(__file__).parent / "frontend" / "static" / "images" / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")

    raise HTTPException(status_code=404, detail="Favicon not found")


@app.on_event("startup")
async def on_startup():
    await check_media_proxy()
    try:
        tasks = await redis_cache.get_all_tasks()
        for task_id, task in tasks.items():
            status = task.video_status.status
            user_id = await redis_cache.get_task_user(task_id)

            if status == VideoDownloadStatus.PENDING:
                if task.download is not None:
                    if user_id:
                        active = await redis_cache.get_user_active_task(user_id)
                        if not active:
                            await redis_cache.acquire_user_active_task(user_id, task_id)
                        elif active != task_id:
                            continue
                    try:

                        arq = await task_queue.get()
                        await arq.enqueue_job("download_video", task_id, _job_id=task_id)
                    except Exception:
                        task.video_status.status = VideoDownloadStatus.ERROR
                        task.video_status.description = "Failed to resume after restart"
                        await redis_cache.set_download_task(task)
                        if user_id:
                            await redis_cache.release_user_active_task(user_id, task_id)
                else:
                    task.video_status.status = VideoDownloadStatus.ERROR
                    task.video_status.description = "Server restarted; task parameters lost. Start a new download."
                    await redis_cache.set_download_task(task)
                    if user_id:
                        await redis_cache.release_user_active_task(user_id, task_id)
            elif status in (VideoDownloadStatus.COMPLETED, VideoDownloadStatus.DONE, VideoDownloadStatus.ERROR,
                            getattr(VideoDownloadStatus, 'CANCELED', 'canceled')):
                if user_id:
                    await redis_cache.release_user_active_task(user_id, task_id)
    except Exception:
        pass
