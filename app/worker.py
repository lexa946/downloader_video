from arq.connections import RedisSettings
from arq import cron

import os
import time
import asyncio
from logging import getLogger
from urllib.parse import urlsplit
from pathlib import Path

from app.models.status import VideoDownloadStatus

from app.config import settings
from app.models.cache import redis_cache
from app.models.services import VideoServicesManager


async def cleanup_old_videos(ctx) -> None:
    """Удаляет видео-файлы, не скачанные пользователем в течение 24 часов.

    Удаляются только задачи в статусе COMPLETED с существующим файлом,
    старше 24 часов. После удаления статус переводится в DONE.
    """
    threshold_seconds = settings.CLEANUP_RETENTION_HOURS * 60 * 60
    now = time.time()

    try:
        tasks = await redis_cache.get_all_tasks()
    except Exception:
        return

    for task_id, task in tasks.items():
        try:
            status = task.video_status.status
            if status == VideoDownloadStatus.PENDING:
                continue

            if status != VideoDownloadStatus.COMPLETED:
                continue

            file_path: Path = task.filepath
            if not file_path or not str(file_path):
                continue
            # На всякий случай привести к Path
            file_path = Path(str(file_path))

            if not file_path.exists():
                # Файл уже удалён (возможно, пользователем) — пропускаем
                continue

            created_at = None
            try:
                created_at = float(getattr(task.video_status, "created_at", None) or 0) or None
            except Exception:
                created_at = None

            # Опорное время: максимально из created_at и mtime файла,
            # чтобы не удалить файл раньше 24ч после его записи на диск
            file_mtime = file_path.stat().st_mtime
            reference_ts = max(created_at or 0, file_mtime)

            if (now - reference_ts) < threshold_seconds:
                continue

            # Удаляем файл и переводим статус в DONE
            try:
                file_path.unlink(missing_ok=True)
            except Exception:
                # Если не смогли удалить — продолжаем к следующей задаче
                continue

            task.video_status.status = VideoDownloadStatus.DONE
            task.video_status.description = VideoDownloadStatus.DONE
            await redis_cache.set_download_task(task)
        except Exception:
            # Не прерываем общий проход по задачам
            continue


async def download_video(ctx, task_id: str):
    task = await redis_cache.get_download_task(task_id)
    if not task or task.video_status.status != VideoDownloadStatus.PENDING:
        return
    service = VideoServicesManager.get_service(task.video_status.video.url)
    parser = service.parser(task.video_status.video.url)
    try:
        await parser.download(task_id, task.download)
    except Exception:
        latest = await redis_cache.get_download_task(task_id)
        if latest and latest.video_status.status == VideoDownloadStatus.PENDING:
            latest.video_status.status = VideoDownloadStatus.ERROR
            latest.video_status.description = "Не удалось скачать видео. Попробуйте ещё раз."
            await redis_cache.set_download_task(latest)
        raise


class WorkerSettings:
    handle_signals = os.name != "nt"
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )
    functions = [download_video]
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = 60 * 60
    health_check_interval = 30

    # Run cleanup daily at 03:00 UTC
    cron_jobs = [
        cron(cleanup_old_videos, hour=3, minute=0),
    ]

    @staticmethod
    async def on_startup(ctx):
        proxy_url = settings.MEDIA_PROXY_URL
        if not proxy_url:
            getLogger(__name__).warning(
                "Mihomo proxy is not configured. YouTube and Instagram use direct connections."
            )
            return
        parsed = urlsplit(proxy_url)
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(parsed.hostname, parsed.port or 80), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            getLogger(__name__).info("Mihomo HTTP proxy is reachable at %s:%s",
                                     parsed.hostname, parsed.port or 80)
        except (OSError, asyncio.TimeoutError, ValueError) as exc:
            getLogger(__name__).error("Mihomo HTTP proxy is unreachable at %s:%s: %s",
                                      parsed.hostname, parsed.port or 80, exc)
