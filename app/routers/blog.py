from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.blog import BlogPost, PostStatus
from app.utils.jinja_filters import ru_date

router = APIRouter(tags=["Blog"])
templates = Jinja2Templates(directory="app/frontend")
templates.env.filters["ru_date"] = ru_date


@router.get("/blog/test/kak-skachat-video-s-youtube-bez-programm", response_class=HTMLResponse)
async def blog_article_youtube(request: Request):
    """Статья о скачивании видео с YouTube"""
    user_id = request.cookies.get("user_id", str(uuid.uuid4()))
    response = templates.TemplateResponse("blog/kak-skachat-video-s-youtube-bez-programm.html", context={"request": request, "user_id": user_id})
    if "user_id" not in request.cookies:
        response.set_cookie("user_id", user_id)
    return response


@router.get("/blog", response_class=HTMLResponse)
async def blog_posts(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(BlogPost)
        .where(BlogPost.status == PostStatus.PUBLISHED)
        .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
    )
    result = await db.execute(stmt)
    posts = result.scalars().all()
    return templates.TemplateResponse("blog/posts.html", {"request": request, "posts": posts})


@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(BlogPost).where(BlogPost.slug == slug, BlogPost.status == PostStatus.PUBLISHED)
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("blog/post_detail.html", {"request": request, "post": post})


