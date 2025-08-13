import uuid

from logging import getLogger
from pathlib import Path as PathLib
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Path, Request
from fastapi.responses import StreamingResponse, Response
from starlette import status
import json
from contextlib import suppress

from app.models.services import VideoServicesManager
from app.models.status import VideoDownloadStatus

from app.models.cache import redis_cache
from app.models.types import DownloadTask
from app.schemas.defaults import EMPTY_VIDEO_RESPONSE
from app.schemas.main import (
    SVideoResponse,
    SVideoRequest,
    SVideoDownload,
    SVideoStatus,
    SYoutubeSearchResponse,
)
from app.utils.video_utils import save_preview_on_s3
from app.utils.validators_utils import check_task_id
from app.utils.video_utils import stream_file

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
            
        # Store in Redis cache
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
async def start_download(request: Request, video_download: SVideoDownload, background_tasks: BackgroundTasks) -> SVideoStatus:
    """Запускает процесс скачивания"""
    user_id = request.cookies.get("user_id", "0")
    task_id = str(uuid.uuid4())

    # Enforce single active download per user using Redis lock
    if user_id and user_id != "0":
        already_active_task = await redis_cache.get_user_active_task(user_id)
        if already_active_task:
            # Validate the active task; if it's stale, clear the lock to allow new download
            try:
                existing = await redis_cache.get_download_task(already_active_task)
            except Exception:
                existing = None
            if (existing is None or
                existing.video_status.status in (VideoDownloadStatus.COMPLETED, VideoDownloadStatus.DONE, VideoDownloadStatus.ERROR) or
                (existing.video_status.status == VideoDownloadStatus.PENDING and existing.download is None)):
                # Release stale lock and continue
                await redis_cache.release_user_active_task(user_id, already_active_task)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="У вас уже есть активная загрузка. Дождитесь завершения текущей загрузки."
                )
    # Get video metadata from cache or fetch it
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
    await redis_cache.set_download_task(task_id, DownloadTask(video_status, download=video_download))
    await redis_cache.add_user_task(user_id, task_id)
    if user_id and user_id != "0":
        # Acquire active lock and store mapping for later release
        acquired = await redis_cache.acquire_user_active_task(user_id, task_id)
        if not acquired:
            # race condition fallback
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="У вас уже есть активная загрузка. Дождитесь завершения текущей загрузки."
            )
        await redis_cache.set_task_user(task_id, user_id)

    service = VideoServicesManager.get_service(video_download.url)
    background_tasks.add_task(service.parser(video_download.url).download, task_id, video_download)
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
            # Отправляем начальный слепок
            task = await redis_cache.get_download_task(task_id)
            if task:
                snap = {"task_id": task_id, **task.video_status.model_dump()}
                yield f"data: {json.dumps(snap)}\n\n"

            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                yield f"data: {data}\n\n"

                # Останавливаемся при завершении
                try:
                    payload = json.loads(data)
                    if payload.get("status") in ("completed", "error", "done"):
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

@router.get("/get-video/{task_id}")
@check_task_id
async def get_downloaded_video(task_id: Annotated[str, Path()]):
    """Отдает файл, если он скачан"""
    task: DownloadTask = await redis_cache.get_download_task(task_id)
    if isinstance(task.filepath, str):
        task.filepath = PathLib(task.filepath)

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
    filename = quote(task.filepath.stem[43:])
    extension = task.filepath.suffix  # Получаем расширение файла (.mp4 или .mp3)
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}{extension}",
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
    try:
        # Lazy import to avoid heavy deps at startup paths
        import aiohttp
        import re
        import json as _json
        from bs4 import BeautifulSoup
        from urllib.parse import quote_plus
        import asyncio

        # Query url
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"

        async with aiohttp.ClientSession(headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
        }) as session:
            async with session.get(search_url) as resp:
                resp.raise_for_status()
                html = await resp.text()

        # Try to parse initial data structure
        yt_initial_json = None
        m = re.search(r"ytInitialData\s*=\s*(\{[\s\S]*?\});", html)
        if m:
            try:
                yt_initial_json = _json.loads(m.group(1))
            except Exception:
                yt_initial_json = None

        items: list[dict] = []
        if yt_initial_json:
            # Walk through contents to find videoRenderer entries
            def walk(obj):
                if isinstance(obj, dict):
                    if "videoRenderer" in obj:
                        items.append(obj["videoRenderer"])
                    for v in obj.values():
                        walk(v)
                elif isinstance(obj, list):
                    for v in obj:
                        walk(v)
            walk(yt_initial_json)
        else:
            # Fallback: parse anchors via BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a#video-title[href^='/watch']"):
                items.append({
                    "navigationEndpoint": {"commandMetadata": {"webCommandMetadata": {"url": a.get("href")}}},
                    "title": {"runs": [{"text": a.get("title") or a.get_text(strip=True)}]},
                })

        # Convert to response items (trim to first page reasonable amount)
        from app.schemas.main import SYoutubeSearchResponse, SYoutubeSearchItem
        result_items: list[SYoutubeSearchItem] = []

        def get_text_runs(runs):
            try:
                return "".join(run.get("text", "") for run in (runs or [])).strip()
            except Exception:
                return ""

        upload_jobs = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # Video URL
            url = None
            try:
                url_path = (
                    it.get("navigationEndpoint", {})
                    .get("commandMetadata", {})
                    .get("webCommandMetadata", {})
                    .get("url")
                )
                if isinstance(url_path, str) and url_path.startswith("/watch"):
                    url = f"https://www.youtube.com{url_path}"
            except Exception:
                pass
            if not url:
                continue

            # Title
            title = get_text_runs((it.get("title") or {}).get("runs")) or ""

            # Author/channel
            author = None
            owner_text = (it.get("longBylineText") or {}).get("runs") or (it.get("ownerText") or {}).get("runs")
            author = get_text_runs(owner_text) if owner_text else None

            # Thumbnails
            thumbnail_url = None
            try:
                thumbs = (it.get("thumbnail") or {}).get("thumbnails", [])
                if thumbs:
                    thumbnail_url = thumbs[-1].get("url")
            except Exception:
                pass

            # Duration
            duration_text = None
            duration_seconds = None
            try:
                duration_text = (it.get("lengthText") or {}).get("simpleText")
                if duration_text:
                    parts = duration_text.split(":")
                    secs = 0
                    for p in parts:
                        secs = secs * 60 + int(p)
                    duration_seconds = secs
            except Exception:
                pass

            result_items.append(SYoutubeSearchItem(
                video_url=url,
                title=title or url,
                author=author,
                duration_text=duration_text,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
            ))

            # S3 upload job for preview if available
            if thumbnail_url:
                upload_jobs.append(save_preview_on_s3(thumbnail_url, title or url, (author or "youtube")))

            if len(result_items) >= 30:
                break

        # Upload previews to S3 concurrently; on failure keep original URL
        if upload_jobs:
            try:
                uploaded_urls = await asyncio.gather(*upload_jobs, return_exceptions=True)
                idx = 0
                for i, item in enumerate(result_items):
                    if item.thumbnail_url:
                        new_url = uploaded_urls[idx]
                        idx += 1
                        if isinstance(new_url, str) and new_url:
                            item.thumbnail_url = new_url
            except Exception:
                pass

        return SYoutubeSearchResponse(items=result_items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube search failed: {e}")
