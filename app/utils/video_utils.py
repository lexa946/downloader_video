import asyncio
import platform
import subprocess
from logging import getLogger
from pathlib import Path

import aiofiles
import aiohttp
from Crypto.Util.py3compat import BytesIO

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.models.storage import DownloadTask
from app.s3.client import s3_client

LOG = getLogger()


if platform.system() == 'Windows':
    FFMPEG = settings.FFMPEG_PATH
else:
    FFMPEG = "ffmpeg"



async def stream_file(file_path: Path, task: DownloadTask, chunk_size: int = 1024 * 1024):
    try:
        async with aiofiles.open(file_path, "rb") as file:
            while chunk := await file.read(chunk_size):
                yield chunk
    finally:
        await asyncio.sleep(1)
        file_path.unlink()
        print(f"Файл {file_path} удален.")
        task.video_status.status = VideoDownloadStatus.DONE
        task.video_status.description = VideoDownloadStatus.DONE


async def save_preview_on_s3(preview_url: str, key: str, folder: str = None) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(preview_url) as resp:
            content = await resp.content.read()
            return s3_client.upload_file(
                key,
                BytesIO(content),
                len(content),
                folder=folder,
                extension=".png",
            )


def combine_audio_and_video(video_path, audio_path, output_path):
    """
    Накладывает аудио на видео.

    Args:
        video_path (str): Путь к исходному видеофайлу.
        audio_path (str): Путь к аудиофайлу, который нужно наложить.
        output_path (str): Путь для сохранения результирующего видеофайла.
    """
    subprocess.run([
        FFMPEG,
        "-i", video_path,  # видео без звука
        "-i", audio_path,  # источник звука
        "-c:v", "copy",  # копируем видео как есть
        "-c:a", "copy",  # копируем аудио как есть (или "aac" для пережатия)
        "-map", "0:v:0",  # берём видео из первого файла
        "-map", "1:a:0",  # берём аудио из второго
        "-shortest",  # обрезаем по короткому
        "-y",  # перезапись без подтверждения
        output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
