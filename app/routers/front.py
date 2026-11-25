from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["Фронт"])

# Настройка путей
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR))


@router.get("/")
async def index(request: Request):
    """Главная Страница"""
    response = templates.TemplateResponse(request, "parsers/index.html")
    return response


@router.get("/youtube-downloader", response_class=HTMLResponse)
async def youtube_downloader(request: Request):
    """Страница YouTube Downloader"""
    response = templates.TemplateResponse(request, "parsers/youtube-downloader.html")
    return response


@router.get("/instagram-downloader", response_class=HTMLResponse)
async def instagram_downloader(request: Request):
    """Страница Instagram Downloader"""
    response = templates.TemplateResponse(request, "parsers/instagram-downloader.html")
    return response


@router.get("/vk-downloader", response_class=HTMLResponse)
async def vk_downloader(request: Request):
    """Страница VK Downloader"""
    response = templates.TemplateResponse(request, "parsers/vk-downloader.html")
    return response


@router.get("/faq", response_class=HTMLResponse)
async def new_faq(request: Request):
    """Страница FAQ"""
    return templates.TemplateResponse(request, "info/faq.html")


@router.get("/privacy", response_class=HTMLResponse)
async def new_privacy(request: Request):
    """Страница политики конфиденциальности"""
    return templates.TemplateResponse(request, "info/privacy.html")


@router.get("/terms", response_class=HTMLResponse)
async def new_terms(request: Request):
    """Страница условий использования"""
    return templates.TemplateResponse(request, "info/terms.html")


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
