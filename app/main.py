from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.routers.service import router as service_router
from app.routers.front import router as new_front_router
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.queue import task_queue

app = FastAPI()

app.include_router(service_router)
app.include_router(new_front_router)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path(__file__).parent / "frontend" / "static" / "images" / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")

    raise HTTPException(status_code=404, detail="Favicon not found")


@app.on_event("startup")
async def on_startup():
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
