import uuid
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["Фронт"])

# Настройка путей
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = FRONTEND_DIR / "static" / "images" / "favicon.png"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/png")

    raise HTTPException(status_code=404, detail="Favicon not found")


@router.get("/")
async def index(request: Request):
    """Главная Страница"""
    user_id = request.cookies.get("user_id", str(uuid.uuid4()))
    response = templates.TemplateResponse("index.html", context={"request": request, "user_id": user_id})
    if "user_id" not in request.cookies:
        response.set_cookie("user_id", user_id)
    return response


@router.get("/faq", response_class=HTMLResponse)
async def new_faq(request: Request):
    """Страница FAQ"""
    return templates.TemplateResponse("faq.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def new_privacy(request: Request):
    """Страница политики конфиденциальности"""
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def new_terms(request: Request):
    """Страница условий использования"""
    return templates.TemplateResponse("terms.html", {"request": request})


@router.get("/robots.txt", response_class=FileResponse)
async def new_robots():
    """Robots.txt для нового фронтенда"""
    robots_file = FRONTEND_DIR / "robots.txt"
    return FileResponse(robots_file, media_type="text/plain")


@router.get("/sitemap.xml", response_class=FileResponse)
async def new_sitemap():
    """Sitemap.xml для нового фронтенда"""
    sitemap_file = FRONTEND_DIR / "sitemap.xml"
    return FileResponse(sitemap_file, media_type="application/xml")


@router.get("/google66673ccfa0013d45.html", response_class=FileResponse)
async def google_verification():
    """Google верификация"""
    google_file = FRONTEND_DIR / "seo" / "google66673ccfa0013d45.html"
    return FileResponse(google_file, media_type="text/html")


@router.get("/yandex_c51849ff7e8fe28a.html", response_class=FileResponse)
async def yandex_verification():
    """Yandex верификация"""
    yandex_file = FRONTEND_DIR / "seo" / "yandex_c51849ff7e8fe28a.html"
    return FileResponse(yandex_file, media_type="text/html")
