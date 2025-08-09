from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.models.blog import BlogPost, PostStatus
from app.schemas.blog import SPostCreate, SPostUpdate
from app.s3.client import s3_client
import io


router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/frontend")


async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get("admin_user_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    admin = await db.get(AdminUser, admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return admin


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username_or_email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AdminUser).where(
        (AdminUser.username == username_or_email) | (AdminUser.email == username_or_email)
    )
    result = await db.execute(stmt)
    admin: Optional[AdminUser] = result.scalar_one_or_none()
    if not admin or not bcrypt.verify(password, admin.password_hash):
        return templates.TemplateResponse(
            "admin/login.html", {"request": request, "error": "Неверные учетные данные"}, status_code=400
        )
    request.session["admin_user_id"] = admin.id
    admin.last_login_at = datetime.utcnow()
    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/posts", response_class=HTMLResponse)
async def posts_index(request: Request, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    result = await db.execute(select(BlogPost).order_by(BlogPost.created_at.desc()))
    posts = result.scalars().all()
    return templates.TemplateResponse("admin/posts.html", {"request": request, "posts": posts})


@router.get("/posts/new", response_class=HTMLResponse)
async def new_post_form(request: Request, admin: AdminUser = Depends(get_current_admin)):
    return templates.TemplateResponse(
        "admin/post_form.html",
        {"request": request, "post": None, "is_edit": False},
    )


@router.post("/posts")
async def create_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    slug: str = Form(...),
    title: str = Form(...),
    subtitle: str | None = Form(None),
    excerpt: str | None = Form(None),
    content: str = Form(...),
    cover_image_url: str | None = Form(None),
    tags: str | None = Form(None),
    language: str = Form("ru"),
    # is_featured removed
    meta_title: str | None = Form(None),
    meta_description: str | None = Form(None),
    og_image_url: str | None = Form(None),
    canonical_url: str | None = Form(None),
    source_url: str | None = Form(None),
    published_at: str | None = Form(None),
):
    tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()] if tags is not None else []
    post = BlogPost(
        slug=slug,
        title=title,
        subtitle=subtitle,
        excerpt=excerpt,
        content=content,
        cover_image_url=cover_image_url,
        tags=tags_list,
        language=language,
        status=PostStatus.DRAFT.value,
        
        meta_title=meta_title,
        meta_description=meta_description,
        og_image_url=og_image_url,
        canonical_url=canonical_url,
        source_url=source_url,
        published_at=datetime.fromisoformat(published_at) if published_at else None,
    )
    db.add(post)
    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.get("/posts/{post_id}/edit", response_class=HTMLResponse)
async def edit_post_form(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "admin/post_form.html",
        {"request": request, "post": post, "is_edit": True, "statuses": list(PostStatus)},
    )


@router.post("/posts/{post_id}")
async def update_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    slug: str = Form(...),
    title: str = Form(...),
    subtitle: str | None = Form(None),
    excerpt: str | None = Form(None),
    content: str = Form(...),
    cover_image_url: str | None = Form(None),
    tags: str | None = Form(None),
    language: str = Form("ru"),
    # is_featured removed
    meta_title: str | None = Form(None),
    meta_description: str | None = Form(None),
    og_image_url: str | None = Form(None),
    canonical_url: str | None = Form(None),
    source_url: str | None = Form(None),
    published_at: str | None = Form(None),
):
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404)

    post.slug = slug
    post.title = title
    post.subtitle = subtitle
    post.excerpt = excerpt
    post.content = content
    post.cover_image_url = cover_image_url
    post.tags = [t.strip() for t in (tags or "").split(",") if t.strip()] if tags is not None else []
    post.language = language
    # статус не меняем из формы; публикация управляется отдельными действиями
    
    post.meta_title = meta_title
    post.meta_description = meta_description
    post.og_image_url = og_image_url
    post.canonical_url = canonical_url
    post.source_url = source_url
    post.published_at = datetime.fromisoformat(published_at) if published_at else None

    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.post("/posts/{post_id}/delete")
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404)
    await db.delete(post)
    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.post("/posts/{post_id}/publish")
async def publish_post(post_id: int, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404)
    post.status = PostStatus.PUBLISHED.value
    post.published_at = datetime.utcnow()
    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.post("/posts/{post_id}/unpublish")
async def unpublish_post(post_id: int, db: AsyncSession = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    post = await db.get(BlogPost, post_id)
    if not post:
        raise HTTPException(status_code=404)
    post.status = PostStatus.DRAFT.value
    post.published_at = None
    await db.commit()
    return RedirectResponse(url="/admin/posts", status_code=302)


@router.post("/upload-image")
async def upload_image(files: List[UploadFile] = File(...), admin: AdminUser = Depends(get_current_admin)):
    urls: list[str] = []
    for f in files:
        content = await f.read()
        name = f.filename or str(uuid.uuid4())
        base, dot, ext = name.rpartition('.')
        key = base or name
        extension = f".{ext}" if ext else ""
        url = s3_client.upload_file(key=key, body=io.BytesIO(content), size=len(content), folder="blog-inline", extension=extension)
        if url:
            urls.append(url)
    return JSONResponse({"urls": urls})


