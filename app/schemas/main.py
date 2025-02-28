from dataclasses import field
from typing import Optional

from pydantic import BaseModel


class SVideoRequest(BaseModel):
    url: str


class SVideo(BaseModel):
    quality: str
    filesize: Optional[int] = field(default=None)
    video_format_id: str
    audio_format_id: str


class SVideoDownload(BaseModel):
    url: str
    audio_format_id: str
    video_format_id: str


class SVideoResponse(BaseModel):
    url: str
    title: str
    formats: list[SVideo]
    preview_url: Optional[str] = field(default=None)
