from arq.connections import RedisSettings

from app.config import settings
from app.models.cache import redis_cache
from app.models.services import VideoServicesManager


async def download_video(ctx, task_id: str):
    task = await redis_cache.get_download_task(task_id)
    if not task:
        return
    service = VideoServicesManager.get_service(task.video_status.video.url)
    parser = service.parser(task.video_status.video.url)
    await parser.download(task_id, task.download)


class WorkerSettings:
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )
    functions = [download_video]
    job_timeout = 60 * 60


