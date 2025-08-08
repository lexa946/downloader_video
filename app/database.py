from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings


Base = declarative_base()


def _get_database_url() -> str | None:
    database_url = getattr(settings, "DATABASE_URL", None)
    if not database_url:
        return None
    # Normalize to async driver if user provided sync URL by mistake
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


DATABASE_URL = _get_database_url()

engine = create_async_engine(DATABASE_URL, future=True, echo=False) if DATABASE_URL else None
SessionLocal: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=AsyncSession)
    if engine
    else None
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database is not configured. Set DATABASE_URL in environment.")
    async with SessionLocal() as session:
        yield session


