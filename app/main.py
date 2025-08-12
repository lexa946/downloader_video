from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.routers.service import router as service_router
from app.routers.user import router as user_router
from app.routers.front import router as new_front_router
from app.routers.admin import router as admin_router
from app.routers.blog import router as blog_router
from app.config import settings
from app.database import engine, Base
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
from app.utils.jinja_filters import ru_date
from fastapi.templating import Jinja2Templates




app = FastAPI()

app.include_router(service_router)
app.include_router(user_router)
app.include_router(new_front_router)
app.include_router(admin_router)
app.include_router(blog_router)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")




app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register Jinja filter
templates = Jinja2Templates(directory="app/frontend")
templates.env.filters["ru_date"] = ru_date


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path(__file__).parent / "frontend" / "static" / "images" / "favicon.png"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/png")

    raise HTTPException(status_code=404, detail="Favicon not found")


@app.on_event("startup")
async def on_startup():
    # create tables if not exist (simple init instead of Alembic)
    if isinstance(engine, AsyncEngine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # bootstrap admin user if no one exists
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from passlib.hash import bcrypt
    from app.models.admin_user import AdminUser
    from app.database import SessionLocal

    if SessionLocal is None:
        return
    async with SessionLocal() as session:  # type: AsyncSession
        result = await session.execute(select(AdminUser))
        admin = result.scalar_one_or_none()
        if admin is None and settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
            admin = AdminUser(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL or f"{settings.ADMIN_USERNAME}@example.com",
                password_hash=bcrypt.hash(settings.ADMIN_PASSWORD),
            )
            session.add(admin)
            await session.commit()
