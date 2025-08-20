from pathlib import Path
import asyncio

from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.routers.service import router as service_router
from app.routers.user import router as user_router
from app.routers.front import router as new_front_router
from app.routers.admin import router as admin_router
from app.routers.blog import router as blog_router
from app.config import settings
from app.database import engine, Base
from sqlalchemy.ext.asyncio import AsyncEngine
from app.utils.jinja_filters import ru_date
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.services import VideoServicesManager
from fastapi.templating import Jinja2Templates

app = FastAPI()

app.include_router(service_router)
app.include_router(user_router)
app.include_router(new_front_router)
app.include_router(admin_router)
app.include_router(blog_router)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register Jinja filter
templates = Jinja2Templates(directory="app/frontend")
templates.env.filters["ru_date"] = ru_date


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path(__file__).parent / "frontend" / "static" / "images" / "favicon.png"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/png")

    raise HTTPException(status_code=404, detail="Favicon not found")


@app.on_event("startup")
async def on_startup():
    if isinstance(engine, AsyncEngine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from passlib.hash import bcrypt
    from app.models.admin_user import AdminUser
    from app.database import SessionLocal

    if SessionLocal is None:
        return
    async with SessionLocal() as session:  # type: AsyncSession
        result = await session.execute(select(AdminUser))
        admin = result.scalar_one_or_none()
        if admin is None and settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
            admin = AdminUser(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL or f"{settings.ADMIN_USERNAME}@example.com",
                password_hash=bcrypt.hash(settings.ADMIN_PASSWORD),
            )
            session.add(admin)
            await session.commit()

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
                        service = VideoServicesManager.get_service(task.video_status.video.url)
                        parser = service.parser(task.video_status.video.url)
                        asyncio.create_task(parser.download(task_id, task.download))
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
