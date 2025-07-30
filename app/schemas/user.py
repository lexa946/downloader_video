from pydantic import BaseModel

from app.schemas.main import SVideoStatus


class SUserHistory(BaseModel):
    history: list[SVideoStatus]