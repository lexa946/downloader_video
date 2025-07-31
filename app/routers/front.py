import uuid

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

router = APIRouter(prefix="", tags=["Фронт"])

templates = Jinja2Templates(directory='app/front')


@router.get('/')
async def index(request: Request):
    user_id = request.cookies.get("user_id", str(uuid.uuid4()))
    response = templates.TemplateResponse(name='service_base.html', context={"request": request, "user_id": user_id})
    if "user_id" not in request.cookies:
        response.set_cookie("user_id", user_id)
    return response

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/front/static/favicon.png")

@router.get("/yandex_c51849ff7e8fe28a.html")
async def yandex_c51849ff7e8fe28a(request: Request):
    return templates.TemplateResponse(name='yandex_c51849ff7e8fe28a.html', context={"request": request})