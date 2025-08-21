import uuid

from logging import getLogger
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette import status
import json
from contextlib import suppress

from app.models.services import VideoServicesManager
from app.models.status import VideoDownloadStatus

from app.models.cache import redis_cache
from app.models.types import DownloadTask
from app.parsers import YouTubeParser
from app.schemas.defaults import EMPTY_VIDEO_RESPONSE
from app.schemas.main import (
    SVideoResponse,
    SVideoRequest,
    SVideoDownload,
    SVideoStatus,
    SYoutubeSearchResponse,
)
from app.utils.validators_utils import check_task_id
from app.utils.video_utils import stream_file
from app.models.queue import task_queue

router = APIRouter(prefix="/api", tags=["Service"])

LOG = getLogger()


@router.post("/get-formats")
async def get_video_formats(video_request: SVideoRequest) -> SVideoResponse:
    """Получаем все доступные форматы видео"""
    try:
        print(f"Service: Processing URL: {video_request.url}")

        # Try to get from Redis cache
        cached_formats = await redis_cache.get_video_meta(video_request.url)
        if cached_formats:
            print(f"Service: Found in cache")
            return cached_formats

        service = VideoServicesManager.get_service(video_request.url)
        print(f"Service: Using service: {service.name}")

        parser_instance = service.parser(video_request.url)
        print(f"Service: Created parser instance")

        available_formats = await parser_instance.get_formats()

        if not available_formats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Can't find formats."
            )
        if not available_formats.formats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No video formats available."
            )

        await redis_cache.set_video_meta(video_request.url, available_formats)
        print(f"Service: Successfully cached and returning {len(available_formats.formats)} formats")
        return available_formats

    except HTTPException:
        raise
    except Exception as e:
        print(f"Service error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/start-download")
async def start_download(request: Request, video_download: SVideoDownload,
                         background_tasks: BackgroundTasks) -> SVideoStatus:
    """Запускает процесс скачивания"""
    user_id = request.cookies.get("user_id", "0")
    task_id = str(uuid.uuid4())

    if user_id and user_id != "0":
        already_active_task = await redis_cache.get_user_active_task(user_id)
        if already_active_task:
            try:
                existing = await redis_cache.get_download_task(already_active_task)
            except Exception:
                existing = None
            if (existing is None or
                    existing.video_status.status in (VideoDownloadStatus.COMPLETED, VideoDownloadStatus.DONE,
                                                     VideoDownloadStatus.ERROR) or
                    (existing.video_status.status == VideoDownloadStatus.PENDING and existing.download is None)):
                await redis_cache.release_user_active_task(user_id, already_active_task)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="У вас уже есть активная загрузка. Дождитесь завершения текущей загрузки."
                )

    video_meta = await redis_cache.get_video_meta(video_download.url)
    if not video_meta:
        service = VideoServicesManager.get_service(video_download.url)
        parser_instance = service.parser(video_download.url)
        video_meta = await parser_instance.get_formats()
        await redis_cache.set_video_meta(video_download.url, video_meta)

    video_status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.PENDING,
        video=video_meta or EMPTY_VIDEO_RESPONSE
    )
    await redis_cache.set_download_task(DownloadTask(video_status, download=video_download))
    await redis_cache.add_user_task(user_id, task_id)
    if user_id and user_id != "0":
        acquired = await redis_cache.acquire_user_active_task(user_id, task_id)
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="У вас уже есть активная загрузка. Дождитесь завершения текущей загрузки."
            )
        await redis_cache.set_task_user(task_id, user_id)

    arq = await task_queue.get()
    await arq.enqueue_job("download_video", task_id, _job_id=task_id)
    return video_status


@router.get("/download-status/{task_id}")
@check_task_id
async def get_download_status(task_id: Annotated[str, Path()]) -> SVideoStatus:
    """Проверяет статус загрузки"""
    task = await redis_cache.get_download_task(task_id)
    return task.video_status


@router.get("/download-events/{task_id}")
@check_task_id
async def download_events(request: Request, task_id: Annotated[str, Path()]):
    """SSE поток обновлений прогресса для задачи скачивания"""
    if not await redis_cache.exist_download_task(task_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    channel = redis_cache.channel_for_task(task_id)
    pubsub = redis_cache.redis.pubsub()
    await pubsub.subscribe(channel)

    async def event_generator():
        try:
            task = await redis_cache.get_download_task(task_id)
            if task:
                snap = {"task_id": task_id, **task.video_status.model_dump()}
                yield f"data: {json.dumps(snap)}\n\n"

            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                yield f"data: {data}\n\n"

                try:
                    payload = json.loads(data)
                    if payload.get("status") in ("completed", "error", "done", "canceled"):
                        break
                except Exception:
                    pass
                if await request.is_disconnected():
                    break
        finally:
            with suppress(Exception):
                await pubsub.unsubscribe(channel)
                await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/cancel/{task_id}")
@check_task_id
async def cancel_download(task_id: Annotated[str, Path()]):
    """Отменяет активную загрузку."""
    task: DownloadTask = await redis_cache.get_download_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.video_status.status = VideoDownloadStatus.CANCELED
    task.video_status.description = "Canceled by user"
    await redis_cache.set_download_task(task)
    await redis_cache.set_task_canceled(task_id)

    user_id = await redis_cache.get_task_user(task_id)
    if user_id:
        await redis_cache.release_user_active_task(user_id, task_id)

    return {"ok": True}


@router.get("/get-video/{task_id}")
@check_task_id
async def get_downloaded_video(task_id: Annotated[str, Path()]):
    """Отдает файл, если он скачан"""
    task: DownloadTask = await redis_cache.get_download_task(task_id)

    if task.video_status.status == VideoDownloadStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="The file is not ready."
        )

    if not task.filepath.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The file does not exist."
        )
    original = task.filepath.stem
    for prefix in (f"{task.id_}_video_", f"{task.id_}_audio_", f"{task.id_}_"):
        if original.startswith(prefix):
            original = original[len(prefix):]
            break
    try:    
        import unicodedata
        display_name = unicodedata.normalize('NFC', original)
    except Exception:
        display_name = original
    if not display_name:
        display_name = "video"
    ascii_fallback = ''.join(ch if (ord(ch) < 128 and ch not in '\\/"\r\n') else '_' for ch in display_name)
    ascii_fallback = ascii_fallback.replace('/', '_')
    encoded_name = quote(display_name)
    extension = task.filepath.suffix

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}{extension}; filename=\"{ascii_fallback}{extension}\"",
        "Content-Length": str(task.filepath.stat().st_size),
        "Cache-Control": "no-cache",
        "Accept-Ranges": "bytes",
    }
    return StreamingResponse(
        stream_file(task.filepath, task),
        media_type="application/octet-stream",
        headers=headers
    )


@router.get("/youtube/search", response_model=SYoutubeSearchResponse)
async def youtube_search(q: str):
    """Поиск по YouTube (первая страница).

    Скрейпит результаты выдачи поискового запроса и возвращает карточки.
    """
    result_items = await YouTubeParser.search_videos(q)
    return SYoutubeSearchResponse(items=result_items)
