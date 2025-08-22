from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin_user import AdminUser
from app.models.blog import BlogPost, PostStatus
from app.schemas.blog import SPostCreate, SPostUpdate
from app.models.cache import redis_cache
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


# ================== REDIS MONITORING ==================
@router.get("/redis/users", response_class=HTMLResponse)
async def redis_users(
    request: Request,
    active: int | None = Query(default=None, description="1=только активные, 0=только неактивные"),
    last_hours: int | None = Query(default=None, description="Показывать активных за последние N часов"),
    sort: str | None = Query(default=None, description="user|active|last|title"),
    dir: str | None = Query(default=None, description="asc|desc"),
    admin: AdminUser = Depends(get_current_admin),
):
    users = await redis_cache.list_users()
    rows_all = []
    for uid in users:
        active_task = await redis_cache.get_user_active_task(uid)
        # берем самую свежую задачу как индикатор последней активности
        task_ids = await redis_cache.get_user_tasks(uid)
        last_task_id = task_ids[0] if task_ids else None
        last_task = await redis_cache.get_download_task(last_task_id) if last_task_id else None
        last_activity_ts = None
        if last_task and getattr(last_task.video_status, "created_at", None):
            try:
                last_activity_ts = float(last_task.video_status.created_at)
            except Exception:
                last_activity_ts = None
        rows_all.append({
            "user_id": uid,
            "active_task": active_task,
            "last_activity_ts": last_activity_ts,
            "last_title": (last_task.video_status.video.title if last_task else None),
            "last_url": (last_task.video_status.video.url if last_task else None),
            "last_status": (last_task.video_status.status if last_task else None),
        })
    # Глобальный счётчик активных пользователей
    active_count = sum(1 for r in rows_all if r["active_task"])

    # Фильтрация
    rows = rows_all
    if active is not None:
        want_active = bool(active)
        rows = [r for r in rows if bool(r["active_task"]) == want_active]
    if last_hours is not None and last_hours >= 0:
        import time as _time
        threshold = _time.time() - (last_hours * 3600)
        rows = [r for r in rows if (r["last_activity_ts"] or 0) >= threshold]

    # Сортировка
    allowed_sorts = {"user", "active", "last"}
    if sort not in allowed_sorts:
        sort = None
    reverse = (dir == "desc") if dir in {"asc", "desc"} else True
    if sort:
        if sort == "user":
            rows.sort(key=lambda r: r["user_id"] or "", reverse=reverse)
        elif sort == "active":
            rows.sort(key=lambda r: 1 if r["active_task"] else 0, reverse=reverse)
        elif sort == "last":
            rows.sort(key=lambda r: float(r["last_activity_ts"] or 0.0), reverse=reverse)
        # title sorting removed with column

    rows_count = len(rows)

    return templates.TemplateResponse(
        "admin/redis_users.html",
        {
            "request": request,
            "rows": rows,
            "active_count": active_count,
            "rows_count": rows_count,
            "filter_active": active,
            "filter_last_hours": last_hours,
            "sort_key": sort,
            "sort_dir": (dir if dir in {"asc", "desc"} else None),
        },
    )


@router.get("/redis/users/{user_id}", response_class=HTMLResponse)
async def redis_user_detail(user_id: str, request: Request, admin: AdminUser = Depends(get_current_admin)):
    active_task_id = await redis_cache.get_user_active_task(user_id)
    active_task = await redis_cache.get_download_task(active_task_id) if active_task_id else None
    task_ids = await redis_cache.get_user_tasks(user_id)
    tasks = []
    for tid in task_ids:
        t = await redis_cache.get_download_task(tid)
        if t:
            try:
                ts = float(getattr(t.video_status, "created_at", 0) or 0)
                t.created_at_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")  # type: ignore[attr-defined]
            except Exception:
                t.created_at_str = ""  # type: ignore[attr-defined]
            tasks.append(t)
    last_activity = None
    if tasks:
        try:
            last_activity = float(getattr(tasks[0].video_status, "created_at", 0) or 0)
        except Exception:
            last_activity = None
    return templates.TemplateResponse(
        "admin/redis_user_detail.html",
        {
            "request": request,
            "user_id": user_id,
            "active_task": active_task,
            "tasks": tasks,
            "last_activity_ts": last_activity,
        },
    )


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


