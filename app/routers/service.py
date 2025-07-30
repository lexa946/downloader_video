import uuid

from logging import getLogger
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from starlette import status

from app.models.services import VideoServicesManager
from app.models.status import VideoDownloadStatus
from app.models.storage import DownloadTask, DOWNLOAD_TASKS, USER_TASKS, VIDEO_META_CACHE
from app.schemas.defaults import EMPTY_VIDEO_RESPONSE
from app.schemas.main import SVideoResponse, SVideoRequest, SVideoDownload, SVideoStatus
from app.utils.validators_utils import check_task_id
from app.utils.video_utils import stream_file

router = APIRouter(prefix="/api", tags=["Service"])

LOG = getLogger()

@router.post("/get-formats")
async def get_video_formats(video_request: SVideoRequest) -> SVideoResponse:
    """Получаем все доступные форматы видео"""
    if video_request.url in VIDEO_META_CACHE:
        return VIDEO_META_CACHE[video_request.url]

    service = VideoServicesManager.get_service(video_request.url)
    available_formats = await service.parser(video_request.url).get_formats()
    if not available_formats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Can't find formats."
        )
    VIDEO_META_CACHE[video_request.url] = available_formats
    return available_formats


@router.post("/start-download")
async def start_download(request: Request, video_download: SVideoDownload, background_tasks: BackgroundTasks) -> SVideoStatus:
    """Запускает процесс скачивания"""
    user_id = request.cookies.get("user_id", "0")
    task_id = str(uuid.uuid4())
    video_status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.PENDING,
        video=VIDEO_META_CACHE.get(video_download.url, EMPTY_VIDEO_RESPONSE)
    )
    DOWNLOAD_TASKS[task_id] = DownloadTask(video_status)
    USER_TASKS[user_id].append(task_id)

    service = VideoServicesManager.get_service(video_download.url)
    background_tasks.add_task(service.parser(video_download.url).download, task_id, video_download)
    return video_status


@router.get("/download-status/{task_id}")
@check_task_id
async def get_download_status(task_id: Annotated[str, Path()]) -> SVideoStatus:
    """Проверяет статус загрузки"""
    return DOWNLOAD_TASKS[task_id].video_status


@router.get("/get-video/{task_id}")
@check_task_id
async def get_downloaded_video(task_id: Annotated[str, Path()]) -> StreamingResponse:
    """Отдает файл, если он скачан"""
    task: DownloadTask = DOWNLOAD_TASKS[task_id]

    if task.video_status.status != VideoDownloadStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="The file is not ready."
        )

    if not task.filepath.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The file does not exist."
        )
    filename = quote(task.filepath.stem)[43:]

    return StreamingResponse(
        stream_file(task.filepath, task),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"attachment; filename={filename}.mp4",
            "Content-Length": str(task.filepath.stat().st_size),
        }
    )
