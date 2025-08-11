import os

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOWNLOAD_FOLDER: str
    FFMPEG_PATH: str
    MIN_VIDEO_HEIGHT: int

    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_ENDPOINT_URL: str
    S3_BUCKET_NAME: str

    INSTAGRAM_CSRFTOKEN: str
    INSTAGRAM_SESSIONID: str

    # Redis settings
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PREFIX: str 
    REDIS_TTL: int

    # Database / Admin / Security
    DATABASE_URL: str
    SECRET_KEY: str
    ADMIN_EMAIL: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str


    @model_validator(mode="before")
    def set_more_field(cls, values):
        os.makedirs(values['DOWNLOAD_FOLDER'], exist_ok=True)
        return values

    class Config:
        env_file = '.env'


settings = Settings()