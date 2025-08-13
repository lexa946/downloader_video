import asyncio
import platform
import subprocess
import sys
from typing import Callable, Optional, Dict
from logging import getLogger
from pathlib import Path

import aiofiles
import aiohttp
from Crypto.Util.py3compat import BytesIO

from app.config import settings
from app.models.cache import redis_cache
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask

from app.s3.client import s3_client

LOG = getLogger()


if platform.system() == 'Windows':
    FFMPEG = settings.FFMPEG_PATH
else:
    FFMPEG = "ffmpeg"



async def stream_file(file_path: Path, task: DownloadTask, chunk_size: int = 1024 * 1024):
    task_id = task.video_status.task_id
    try:
        async with aiofiles.open(file_path, "rb") as file:
            while chunk := await file.read(chunk_size):
                yield chunk
    finally:
        await asyncio.sleep(1)
        file_path.unlink()
        print(f"Video Utils: stream_file - {file_path} is deleted.")
        task.video_status.status = VideoDownloadStatus.DONE
        task.video_status.description = VideoDownloadStatus.DONE
        await redis_cache.set_download_task(task_id, task)


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


def convert_to_mp3(input_path: str, output_path: str):
    """
    Конвертирует аудио в MP3 формат.

    Args:
        input_path (str): Путь к исходному аудио файлу
        output_path (str): Путь для сохранения MP3
    """
    subprocess.run([
        FFMPEG,
        "-i", input_path,
        "-vn",  # отключаем видео
        "-acodec", "libmp3lame",  # используем MP3 кодек
        "-q:a", "2",  # качество VBR (0-9, где 0 лучшее)
        "-y",  # перезапись без подтверждения
        output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cut_media(input_path: str,
              output_path: str,
              start_seconds: Optional[int] = None,
              end_seconds: Optional[int] = None):
    """
    Безперекодировочная обрезка файла по времени.

    Если задан только start_seconds — отрезает от start до конца.
    Если задан только end_seconds — отрезает от начала до end.
    Если заданы оба — отрезает интервал [start, end).
    """
    cmd = [FFMPEG]
    if start_seconds is not None:
        cmd += ["-ss", str(start_seconds)]
    if end_seconds is not None:
        cmd += ["-to", str(end_seconds)]
    cmd += ["-i", input_path, "-c", "copy", "-y", output_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _build_ffmpeg_headers_arg(headers: Optional[Dict[str, str]]) -> list[str]:
    if not headers:
        return []
    # ffmpeg expects CRLF-separated header lines in one string after -headers
    header_lines = []
    for key, value in headers.items():
        header_lines.append(f"{key}: {value}")
    header_blob = "\r\n".join(header_lines)
    return ["-headers", header_blob]


def download_hls_to_file(hls_url: str,
                         output_path: str,
                         duration_seconds: int,
                         on_progress: Optional[Callable[[float, float], None]] = None,
                         headers: Optional[Dict[str, str]] = None) -> None:
    """
    Загрузка HLS-потока через ffmpeg с прогрессом.

    - hls_url: URL мастер/вариант m3u8
    - output_path: путь к результирующему MP4
    - duration_seconds: длительность контента (секунды) для расчета процента
    - on_progress: callback(seconds_done, percent)
    - headers: HTTP заголовки для запроса
    """
    cmd = [
        FFMPEG,
        *(_build_ffmpeg_headers_arg(headers)),
        "-i", hls_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-loglevel", "error",
        "-y",
        output_path,
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    seconds_done = 0.0
    percent = 0.0
    try:
        if process.stdout is not None:
            for line in process.stdout:
                line = line.strip()
                # ffmpeg -progress outputs key=value lines
                # we look for out_time_ms
                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = float(line.split("=", 1)[1])
                        seconds_done = out_time_ms / 1_000_000.0
                        if duration_seconds and duration_seconds > 0:
                            percent = max(0.0, min(100.0, (seconds_done / duration_seconds) * 100.0))
                        else:
                            percent = 0.0
                        if on_progress:
                            on_progress(seconds_done, percent)
                    except Exception:
                        # Ignore parse errors, continue
                        pass
                elif line == "progress=end":
                    # Completed
                    percent = 100.0
                    if on_progress:
                        on_progress(seconds_done, percent)
        # Wait for process to exit
        process.wait()
        if process.returncode != 0:
            # capture stderr for diagnostics
            err = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"ffmpeg failed with code {process.returncode}: {err}")
    finally:
        try:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        except Exception:
            pass


def download_hls_av_to_file(video_hls_url: str,
                            audio_hls_url: str,
                            output_path: str,
                            duration_seconds: int,
                            on_progress: Optional[Callable[[float, float], None]] = None,
                            headers: Optional[Dict[str, str]] = None) -> None:
    """
    Загрузка раздельных HLS дорожек (видео + аудио) и муксинг в один MP4.
    """
    headers_arg = _build_ffmpeg_headers_arg(headers)

    cmd = [
        FFMPEG,
        *headers_arg, "-i", video_hls_url,
        *headers_arg, "-i", audio_hls_url,
        "-c:v", "copy",
        "-c:a", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-loglevel", "error",
        "-y",
        output_path,
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    seconds_done = 0.0
    percent = 0.0
    try:
        if process.stdout is not None:
            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = float(line.split("=", 1)[1])
                        seconds_done = out_time_ms / 1_000_000.0
                        if duration_seconds and duration_seconds > 0:
                            percent = max(0.0, min(100.0, (seconds_done / duration_seconds) * 100.0))
                        else:
                            percent = 0.0
                        if on_progress:
                            on_progress(seconds_done, percent)
                    except Exception:
                        pass
                elif line == "progress=end":
                    percent = 100.0
                    if on_progress:
                        on_progress(seconds_done, percent)
        process.wait()
        if process.returncode != 0:
            err = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"ffmpeg failed with code {process.returncode}: {err}")
    finally:
        try:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        except Exception:
            pass
