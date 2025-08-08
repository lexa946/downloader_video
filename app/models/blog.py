from __future__ import annotations

import enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func

from app.database import Base


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    excerpt = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    cover_image_url = Column(Text, nullable=True)

    tags = Column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    language = Column(String(10), nullable=False, server_default="ru")

    status = Column(String(16), nullable=False, server_default=PostStatus.DRAFT.value)
    view_count = Column(Integer, nullable=False, server_default=text("0"))

    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)
    og_image_url = Column(Text, nullable=True)
    canonical_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_blog_posts_status_published_at", "status", "published_at"),
        Index("ix_blog_posts_created_at", "created_at"),
    )


