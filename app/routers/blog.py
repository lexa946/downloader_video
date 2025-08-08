from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.blog import BlogPost, PostStatus


router = APIRouter(tags=["Blog"])
templates = Jinja2Templates(directory="app/frontend")


@router.get("/blog/posts", response_class=HTMLResponse)
async def blog_posts(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(BlogPost)
        .where(BlogPost.status == PostStatus.PUBLISHED)
        .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
    )
    result = await db.execute(stmt)
    posts = result.scalars().all()
    return templates.TemplateResponse("blog/posts.html", {"request": request, "posts": posts})


@router.get("/blog/posts/{slug}", response_class=HTMLResponse)
async def blog_post_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(BlogPost).where(BlogPost.slug == slug, BlogPost.status == PostStatus.PUBLISHED)
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("blog/post_detail.html", {"request": request, "post": post})


