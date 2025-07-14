import platform
import subprocess
from uuid import uuid4

import aiohttp
from Crypto.Util.py3compat import BytesIO

from pytubefix import Stream


from app.config import settings
from app.s3.client import s3_client

from app.schemas.main import SVideo



if platform.system() == 'Windows':
    FFMPEG = settings.FFMPEG_PATH
else:
    FFMPEG = "ffmpeg"


def format_filter(stream: Stream):
    return (
        stream.type == "video" and
        stream.video_codec.startswith("avc1") and
        stream.height > settings.MIN_VIDEO_HEIGHT
    )


def get_formats(streams: list[Stream], audio_stream: Stream):
    formats_all = list(filter(format_filter, streams))
    available_formats = [
        SVideo(
            **{
                "quality": v_format.resolution,
                "video_format_id": v_format.itag,
                "audio_format_id": audio_stream.itag,
                "filesize": round(v_format.filesize_mb + audio_stream.filesize_mb/2, 2),
            }
        ) for v_format in formats_all
    ]
    return available_formats


async def save_preview_on_s3(preview_url: str, video_title: str) -> str:
    video_title = video_title.strip(" ?./\\|")
    async with aiohttp.ClientSession() as session:
        async with session.get(preview_url) as resp:
            content = await resp.content.read()
            return s3_client.upload_file(
                f"{str(uuid4())}_{video_title}.png",
                BytesIO(content),
                len(content)
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
