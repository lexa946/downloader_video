import asyncio
import platform
import uuid
from concurrent.futures import ProcessPoolExecutor

from pathlib import Path
from logging import getLogger
from typing import Annotated

import yt_dlp
from fastapi import APIRouter, Depends, BackgroundTasks

from starlette.responses import StreamingResponse

from app.config import settings
from app.schemas.main import SVideoResponse, SVideoRequest, SVideoDownload
from app.utils.helpers import get_formats

router = APIRouter(prefix="/api", tags=["Service"])

LOG = getLogger()

download_tasks = {}


@router.get("/get-formats")
async def get_video_formats(video: Annotated[SVideoRequest, Depends()]) -> SVideoResponse:
    loop = asyncio.get_running_loop()

    def extract_info():
        ydl_opts = {'quiet': True, 'noplaylist': True, 'nocheckcertificate': True, }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video.url, download=False)

    info = await loop.run_in_executor(None, extract_info)

    available_formats = get_formats(info)

    return SVideoResponse(
        url=video.url,
        title=info['title'],
        preview_url=info['thumbnail'],
        formats=available_formats
    )


async def download_video_task(task_id: str, download_video: SVideoDownload):
    loop = asyncio.get_running_loop()

    ydl_opts = {
        'concurrent_fragments': 16,
        'outtmpl': f"{settings.DOWNLOAD_FOLDER}/"
                   f"%(uploader)s/"
                   f"{download_video.video_format_id}_%(upload_date>%Y-%m-%d)s_%(uploader)s#%(title)s.%(ext)s",
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'nocheckcertificate': True,
        'quiet': True,
        'throttled_rate': '500K',
        'socket_timeout': 30,
        'extract_flat': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        },
        'format': download_video.video_format_id,
    }

    if download_video.audio_format_id:
        ydl_opts['format'] = ydl_opts['format'] + "+" + download_video.audio_format_id

    if platform.system() == 'Windows':
        ydl_opts['ffmpeg_location'] = settings.FFMPEG_PATH

    def post_process_hook(d):
        download_tasks[task_id]["percent"] = d['_percent_str'].strip()

    ydl_opts['progress_hooks'] = [post_process_hook]

    ydl = yt_dlp.YoutubeDL(ydl_opts)

    def download():
        return ydl.extract_info(download_video.url, download=True)

    try:
        info = await loop.run_in_executor(None, download)
        filename = Path(ydl.prepare_filename(info))
        download_tasks[task_id] = {"status": "completed", "file_path": filename}
    except Exception as e:
        download_tasks[task_id] = {"status": "failed", "error": str(e)}
    finally:
        ydl.restore_console_title()
        ydl.close()


async def stream_file(file_path: Path, chunk_size: int = 1024 * 1024):
    try:
        with file_path.open("rb") as file:
            while chunk := file.read(chunk_size):
                yield chunk
    finally:
        await asyncio.sleep(1)
        file_path.unlink()
        LOG.info(f"Файл {file_path} удален.")


@router.post("/start-download")
async def start_download(request: SVideoDownload, background_tasks: BackgroundTasks):
    """Запускает процесс скачивания"""
    task_id = str(uuid.uuid4())  # Генерируем уникальный ID задачи
    download_tasks[task_id] = {"status": "pending"}

    background_tasks.add_task(download_video_task, task_id, request)
    return {"task_id": task_id}


@router.get("/download-status/{task_id}")
async def get_download_status(task_id: str):
    """Проверяет статус загрузки"""
    return download_tasks.get(task_id, {"status": "not_found"})


@router.get("/get-video/{task_id}")
async def get_downloaded_video(task_id: str):
    """Отдает файл, если он скачан"""
    task_info = download_tasks.get(task_id)

    if not task_info or task_info["status"] != "completed":
        return {"error": "Файл еще не готов"}

    file_path = task_info["file_path"]

    if not file_path.exists():
        return {"error": "Файл не найден"}

    return StreamingResponse(
        stream_file(file_path),
        media_type="video/mp4",
        headers={"Content-Disposition": "attachment; filename=video.mp4"}
    )
