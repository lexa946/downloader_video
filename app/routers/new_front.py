import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(prefix="/new", tags=["Новый Фронт"])

# Настройка путей
NEW_FRONTEND_DIR = Path(__file__).parent.parent / "new_frontend"
templates = Jinja2Templates(directory=str(NEW_FRONTEND_DIR))

# Статические файлы
@router.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    """Обслуживание статических файлов"""
    static_file_path = NEW_FRONTEND_DIR / "static" / file_path
    if static_file_path.exists() and static_file_path.is_file():
        return FileResponse(static_file_path)
    return FileResponse(NEW_FRONTEND_DIR / "static" / "css" / "styles.css")  # Fallback

@router.get("/", response_class=HTMLResponse)
async def new_index(request: Request):
    """Новая главная страница"""
    # Читаем HTML файл напрямую для полного контроля над контентом
    html_file = NEW_FRONTEND_DIR / "index.html"
    
    if html_file.exists():
        content = html_file.read_text(encoding='utf-8')
        
        # Заменяем относительные пути на абсолютные для статики
        content = content.replace('href="/static/', 'href="/new/static/')
        content = content.replace('src="/static/', 'src="/new/static/')
        content = content.replace('href="/favicon.ico"', 'href="/favicon.ico"')
        
        return HTMLResponse(content=content)
    
    return HTMLResponse(content="<h1>Новый фронтенд не найден</h1>", status_code=404)

@router.get("/faq", response_class=HTMLResponse)
async def new_faq():
    """Страница FAQ"""
    html_file = NEW_FRONTEND_DIR / "faq.html"
    
    if html_file.exists():
        content = html_file.read_text(encoding='utf-8')
        content = content.replace('href="/static/', 'href="/new/static/')
        content = content.replace('src="/static/', 'src="/new/static/')
        content = content.replace('href="/"', 'href="/new/"')
        return HTMLResponse(content=content)
    
    return HTMLResponse(content="<h1>FAQ не найден</h1>", status_code=404)

@router.get("/privacy", response_class=HTMLResponse)
async def new_privacy():
    """Страница политики конфиденциальности"""
    html_file = NEW_FRONTEND_DIR / "privacy.html"
    
    if html_file.exists():
        content = html_file.read_text(encoding='utf-8')
        content = content.replace('href="/static/', 'href="/new/static/')
        content = content.replace('src="/static/', 'src="/new/static/')
        content = content.replace('href="/"', 'href="/new/"')
        return HTMLResponse(content=content)
    
    return HTMLResponse(content="<h1>Политика конфиденциальности не найдена</h1>", status_code=404)

@router.get("/terms", response_class=HTMLResponse)
async def new_terms():
    """Страница условий использования"""
    html_file = NEW_FRONTEND_DIR / "terms.html"
    
    if html_file.exists():
        content = html_file.read_text(encoding='utf-8')
        content = content.replace('href="/static/', 'href="/new/static/')
        content = content.replace('src="/static/', 'src="/new/static/')
        content = content.replace('href="/"', 'href="/new/"')
        content = content.replace('href="/privacy"', 'href="/new/privacy"')
        return HTMLResponse(content=content)
    
    return HTMLResponse(content="<h1>Условия использования не найдены</h1>", status_code=404)

@router.get("/robots.txt", response_class=FileResponse)
async def new_robots():
    """Robots.txt для нового фронтенда"""
    robots_file = NEW_FRONTEND_DIR / "robots.txt"
    if robots_file.exists():
        return FileResponse(robots_file, media_type="text/plain")
    return FileResponse(NEW_FRONTEND_DIR.parent / "front" / "templates" / "robots.txt")

@router.get("/sitemap.xml", response_class=FileResponse)
async def new_sitemap():
    """Sitemap.xml для нового фронтенда"""
    sitemap_file = NEW_FRONTEND_DIR / "sitemap.xml"
    if sitemap_file.exists():
        return FileResponse(sitemap_file, media_type="application/xml")
    return FileResponse(NEW_FRONTEND_DIR.parent / "front" / "templates" / "sitemap.xml")

# Мета-теги для поисковиков (если нужны отдельные файлы)
@router.get("/google66673ccfa0013d45.html", response_class=FileResponse)
async def google_verification():
    """Google верификация"""
    google_file = NEW_FRONTEND_DIR.parent / "front" / "templates" / "google66673ccfa0013d45.html"
    if google_file.exists():
        return FileResponse(google_file, media_type="text/html")
    return HTMLResponse(content="google-site-verification: google66673ccfa0013d45.html")

@router.get("/yandex_c51849ff7e8fe28a.html", response_class=FileResponse) 
async def yandex_verification():
    """Yandex верификация"""
    yandex_file = NEW_FRONTEND_DIR.parent / "front" / "templates" / "yandex_c51849ff7e8fe28a.html"
    if yandex_file.exists():
        return FileResponse(yandex_file, media_type="text/html")
    return HTMLResponse(content="<html><head><meta name='yandex-verification' content='c51849ff7e8fe28a' /></head></html>")

# Дополнительные роуты для удобства
@router.get("/favicon.ico", include_in_schema=False)
async def new_favicon():
    """Favicon для нового фронтенда"""
    # Сначала пробуем найти в новом фронтенде
    favicon_path = NEW_FRONTEND_DIR / "static" / "images" / "favicon.png"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/png")
    
    # Если нет, используем из старого фронтенда
    favicon_path_old = NEW_FRONTEND_DIR.parent / "front" / "static" / "images" / "favicon.png"
    if favicon_path_old.exists():
        return FileResponse(favicon_path_old, media_type="image/png")
    
    # Если нигде нет, возвращаем 404
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Favicon not found")