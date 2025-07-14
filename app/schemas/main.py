from dataclasses import field
from typing import Optional

from pydantic import BaseModel


class SVideoRequest(BaseModel):
    url: str


class SVideo(BaseModel):
    quality: str
    filesize: Optional[int] = field(default=0)
    video_format_id: str
    audio_format_id: str


class SVideoDownload(BaseModel):
    url: str
    video_format_id: str
    audio_format_id: str


class SVideoFormatsResponse(BaseModel):
    url: str
    title: str
    formats: list[SVideo]
    preview_url: Optional[str] = field(default=None)


class SVideoStatus(BaseModel):
    task_id: str
    status: str
    description: str = field(default=None)
    percent: float = field(default=0)

