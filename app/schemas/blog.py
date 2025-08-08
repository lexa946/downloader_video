from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.blog import PostStatus


class SPostBase(BaseModel):
    slug: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=500)
    content: str
    cover_image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    language: str = Field(default="ru", max_length=10)
    status: PostStatus = Field(default=PostStatus.DRAFT)
    is_featured: bool = False
    meta_title: Optional[str] = Field(default=None, max_length=255)
    meta_description: Optional[str] = Field(default=None, max_length=500)
    og_image_url: Optional[str] = None
    canonical_url: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None


class SPostCreate(SPostBase):
    pass


class SPostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    cover_image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    language: Optional[str] = Field(default=None, max_length=10)
    status: Optional[PostStatus] = None
    is_featured: Optional[bool] = None
    meta_title: Optional[str] = Field(default=None, max_length=255)
    meta_description: Optional[str] = Field(default=None, max_length=500)
    og_image_url: Optional[str] = None
    canonical_url: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None


class SPostOut(SPostBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


