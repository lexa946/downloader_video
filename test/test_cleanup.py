import asyncio
import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import settings
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.schemas.main import SVideoStatus, SVideoResponse
from app.worker import cleanup_old_videos


@pytest.mark.asyncio
async def test_cleanup_removes_stale_completed_and_sets_done(tmp_path, monkeypatch):
    # Подменим DOWNLOAD_FOLDER на временный
    monkeypatch.setattr(settings, "DOWNLOAD_FOLDER", tmp_path.as_posix())
    # Изолируем ключи Redis отдельным префиксом
    test_prefix = f"test:{uuid4()}:"
    monkeypatch.setattr(settings, "REDIS_PREFIX", test_prefix)
    # Очистим потенциальные ключи под этим префиксом
    async for k in redis_cache.redis.scan_iter(f"{test_prefix}*"):
        await redis_cache.redis.delete(k)
    file_path = tmp_path / "author" / "test.mp4"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * 10)

    # Сделаем mtime глубоко старым
    # Сузим окно до 1 часа, чтобы ускорить тест
    monkeypatch.setattr(settings, "CLEANUP_RETENTION_HOURS", 1)
    old_ts = time.time() - (2 * 60 * 60)
    os_utime = __import__("os").utime
    os_utime(file_path.as_posix(), (old_ts, old_ts))

    task_id = "task-cleanup-1"
    status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.COMPLETED,
        video=SVideoResponse(url="u", title="t", author="a", formats=[], duration=0),
        created_at=old_ts,
    )
    task = DownloadTask(video_status=status, filepath=file_path)
    await redis_cache.set_download_task(task)

    # Выполнить очистку
    await cleanup_old_videos(None)

    # Файл должен быть удалён, статус — DONE
    t = await redis_cache.get_download_task(task_id)
    assert t is not None
    assert t.video_status.status == VideoDownloadStatus.DONE
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_cleanup_keeps_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOWNLOAD_FOLDER", tmp_path.as_posix())
    test_prefix = f"test:{uuid4()}:"
    monkeypatch.setattr(settings, "REDIS_PREFIX", test_prefix)
    async for k in redis_cache.redis.scan_iter(f"{test_prefix}*"):
        await redis_cache.redis.delete(k)

    file_path = tmp_path / "author" / "test2.mp4"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * 10)

    task_id = "task-cleanup-2"
    status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.PENDING,
        video=SVideoResponse(url="u", title="t", author="a", formats=[], duration=0),
        created_at=time.time() - (72 * 60 * 60),
    )
    task = DownloadTask(video_status=status, filepath=file_path)
    await redis_cache.set_download_task(task)

    await cleanup_old_videos(None)

    t = await redis_cache.get_download_task(task_id)
    assert t is not None
    assert t.video_status.status == VideoDownloadStatus.PENDING
    assert file_path.exists()


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOWNLOAD_FOLDER", tmp_path.as_posix())
    test_prefix = f"test:{uuid4()}:"
    monkeypatch.setattr(settings, "REDIS_PREFIX", test_prefix)
    async for k in redis_cache.redis.scan_iter(f"{test_prefix}*"):
        await redis_cache.redis.delete(k)

    file_path = tmp_path / "author" / "test3.mp4"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * 10)

    task_id = "task-cleanup-3"
    status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.COMPLETED,
        video=SVideoResponse(url="u", title="t", author="a", formats=[], duration=0),
        created_at=time.time() - (2 * 60 * 60),
    )
    task = DownloadTask(video_status=status, filepath=file_path)
    await redis_cache.set_download_task(task)

    await cleanup_old_videos(None)

    t = await redis_cache.get_download_task(task_id)
    assert t is not None
    assert t.video_status.status == VideoDownloadStatus.COMPLETED
    assert file_path.exists()

