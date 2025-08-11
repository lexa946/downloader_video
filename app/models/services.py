from fastapi import HTTPException
from starlette import status

from app.parsers import YouTubeParser, InstagramParser, VkParser, RutubeParser


class VideoServiceBase:
    name = "VideoService"
    key_words = list()
    parser = None

    @classmethod
    def match_url(cls, url: str) -> bool:
        return any(keyword in url for keyword in cls.key_words)


class YoutubeVideoService(VideoServiceBase):
    name = "YouTube"
    key_words = ['youtube', 'youtu.be', 'shorts']
    parser = YouTubeParser


class InstagramVideoService(VideoServiceBase):
    name = "Instagram"
    key_words = ['instagram', 'reels']
    parser = InstagramParser


class VkVideoService(VideoServiceBase):
    name = "VK"
    key_words = ['vkvideo', 'vk.com/video']
    parser = VkParser


class RutubeVideoService(VideoServiceBase):
    name = "RuTube"
    key_words = [
        'rutube.ru',
        'rutube.ru/video',
        'rutube',
        'rutube.ru/play',
        'rutube.ru/embed',
    ]
    parser = RutubeParser


class VideoServicesManager:
    @classmethod
    def get_service(cls, url):
        for service in VideoServiceBase.__subclasses__():
            if service.match_url(url):
                return service
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video service"
        )