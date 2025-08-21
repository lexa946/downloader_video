import asyncio

from app.models.cache import redis_cache
from app.models.types import DownloadTask
from app.schemas.main import SVideoDownload
from app.utils.video_utils import cut_media


class PostPrecess:
    def __init__(self, task: DownloadTask, download_video: SVideoDownload):
        self.task = task
        self.download_video = download_video


    async def process(self):
        await self.clip()

    async def clip(self):
        if self.download_video.start_seconds is not None or self.download_video.end_seconds is not None:
            self.task.video_status.description = "Clipping selected fragment"
            await redis_cache.set_download_task(self.task)

            clipped_path = self.task.filepath.with_name(self.task.filepath.stem + "_clip" + self.task.filepath.suffix)
            await asyncio.to_thread(
                cut_media,
                self.task.filepath.as_posix(),
                clipped_path.as_posix(),
                self.download_video.start_seconds,
                self.download_video.end_seconds,
            )
            self.task.filepath.unlink(missing_ok=True)
            self.task.filepath = clipped_path
