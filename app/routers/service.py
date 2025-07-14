import uuid

from logging import getLogger
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Path
from fastapi.responses import StreamingResponse
from starlette import status

from app.models.status import VideoDownloadStatus
from app.models.storage import DownloadTask, DOWNLOAD_TASKS
from app.process.video import download_video_task, stream_file, get_available_formats
from app.schemas.main import SVideoResponse, SVideoRequest, SVideoDownload, SVideoStatus
from app.utils.validators_utils import check_task_id

router = APIRouter(prefix="/api", tags=["Service"])

LOG = getLogger()



@router.get("/get-formats")
async def get_video_formats(video: Annotated[SVideoRequest, Depends()]) -> SVideoResponse:
    """Получаем все доступные форматы видео"""
    available_formats = await get_available_formats(video.url)
    return available_formats



@router.post("/start-download")
async def start_download(request: SVideoDownload, background_tasks: BackgroundTasks) -> SVideoStatus:
    """Запускает процесс скачивания"""
    task_id = str(uuid.uuid4())
    video_status = SVideoStatus(
        task_id=task_id,
        status=VideoDownloadStatus.PENDING,
    )
    DOWNLOAD_TASKS[task_id] = DownloadTask(video_status)
    background_tasks.add_task(download_video_task, task_id, request)
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
    filename = quote(task.filepath.stem)[44:]

    return StreamingResponse(
        stream_file(task.filepath),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"attachment; filename={filename}.mp4",
            "Content-Length": str(task.filepath.stat().st_size),
        }
    )
