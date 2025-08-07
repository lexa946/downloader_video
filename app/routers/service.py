import uuid

from logging import getLogger
from pathlib import Path as PathLib
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Path, Request
from fastapi.responses import StreamingResponse, Response
from starlette import status

from app.models.services import VideoServicesManager
from app.models.status import VideoDownloadStatus

from app.models.cache import redis_cache
from app.models.types import DownloadTask
from app.schemas.defaults import EMPTY_VIDEO_RESPONSE
from app.schemas.main import SVideoResponse, SVideoRequest, SVideoDownload, SVideoStatus
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
    await redis_cache.set_download_task(task_id, DownloadTask(video_status))
    await redis_cache.add_user_task(user_id, task_id)

    service = VideoServicesManager.get_service(video_download.url)
    background_tasks.add_task(service.parser(video_download.url).download, task_id, video_download)
    return video_status


@router.get("/download-status/{task_id}")
@check_task_id
async def get_download_status(task_id: Annotated[str, Path()]) -> SVideoStatus:
    """Проверяет статус загрузки"""
    task = await redis_cache.get_download_task(task_id)
    return task.video_status


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
