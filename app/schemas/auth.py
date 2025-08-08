from pydantic import BaseModel, EmailStr


class SAdminLogin(BaseModel):
    username_or_email: str
    password: str


