from abc import ABC, abstractmethod

from app.schemas.main import SVideoResponse, SVideoDownload


class BaseParser(ABC):

    @abstractmethod
    def __init__(self, url):
        ...

    @abstractmethod
    async def get_formats(self, *args, **kwargs) -> SVideoResponse:
        ...



    @abstractmethod
    async def download(self, task_id: str, download_video: SVideoDownload):
        ...