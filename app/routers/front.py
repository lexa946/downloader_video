from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="", tags=["Фронт"])

templates = Jinja2Templates(directory='app/front')


@router.get('/')
async def index(request: Request):
    return templates.TemplateResponse(name='service_base.html', context={'request': request})

