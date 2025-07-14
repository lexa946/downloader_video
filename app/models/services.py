from fastapi import HTTPException
from starlette import status

from app.parsers import YouTubeParser, InstagramParser


class VideoService:
    name = "VideoService"
    key_words = list()
    parser = None

    @classmethod
    def match_url(cls, url: str) -> bool:
        return any(keyword in url for keyword in cls.key_words)


class YoutubeVideoService(VideoService):
    name = "YouTube"
    key_words = ['youtube', 'youtu.be', 'shorts']
    parser = YouTubeParser



class InstagramVideoService(VideoService):
    name = "Instagram"
    key_words = ['instagram', 'reels']
    parser = InstagramParser


class VideoServices:
    YOUTUBE = YoutubeVideoService
    INSTAGRAM = InstagramVideoService

    @classmethod
    def all(cls):
        return [cls.YOUTUBE, cls.INSTAGRAM]


    @classmethod
    def get_service(cls, url):
        for service in VideoServices.all():
            if service.match_url(url):
                return service
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video service"
        )