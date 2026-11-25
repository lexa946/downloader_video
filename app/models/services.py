from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette import status

from app.parsers import YouTubeParser, InstagramParser, VkParser


class VideoServiceBase:
    name = "VideoService"
    domains = ()
    parser = None

    @classmethod
    def match_url(cls, url: str) -> bool:
        try:
            address = urlsplit(url)
            host = address.hostname
        except ValueError:
            return False
        return address.scheme in ("http", "https") and host is not None and any(
            host == domain or host.endswith("." + domain) for domain in cls.domains
        )


class YoutubeVideoService(VideoServiceBase):
    name = "YouTube"
    domains = ("youtube.com", "youtu.be")
    parser = YouTubeParser


class InstagramVideoService(VideoServiceBase):
    name = "Instagram"
    domains = ("instagram.com",)
    parser = InstagramParser


class VkVideoService(VideoServiceBase):
    name = "VK"
    domains = ("vk.com", "vkvideo.ru")
    parser = VkParser


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
