from collections import deque
from typing import Dict

from app.models.services import VideoServicesManager
from app.models.status import VideoDownloadStatus
from app.schemas.main import SVideoDownload
from app.schemas.defaults import EMPTY_VIDEO_STATUS
from app.models.types import DownloadTask
from app.models.cache import redis_cache


class DownloadTasks:
    def __getitem__(self, item: str) -> DownloadTask:
        task = redis_cache.get_download_task(item)
        if task is None:
            return DownloadTask(EMPTY_VIDEO_STATUS)
        return task

    def __setitem__(self, key: str, value: DownloadTask):
        redis_cache.set_download_task(key, value)

    def __contains__(self, item: str) -> bool:
        return redis_cache.get_download_task(item) is not None


class UserTasks:
    def __getitem__(self, user_id: str) -> deque:
        tasks = redis_cache.get_user_tasks(user_id)
        return tasks

    def __setitem__(self, user_id: str, task_id: str):
        redis_cache.add_user_task(user_id, task_id)


async def restore_pending_tasks():
    """Восстанавливает незавершенные задачи после перезапуска сервера"""
    tasks: Dict[str, DownloadTask] = redis_cache.get_all_tasks()
    for task_id, task in tasks.items():
        if task.video_status.status in [VideoDownloadStatus.PENDING, VideoDownloadStatus.ERROR]:
            # Получаем сервис для URL
            service = VideoServicesManager.get_service(task.video_status.video.url)
            # Создаем новую задачу для скачивания
            video_format = next(
                (f for f in task.video_status.video.formats 
                 if f.video_format_id == task.video_status.video.formats[0].video_format_id),
                task.video_status.video.formats[0]
            )
            download_request = SVideoDownload(
                url=task.video_status.video.url,
                video_format_id=video_format.video_format_id,
                audio_format_id=video_format.audio_format_id
            )
            # Запускаем скачивание заново
            await service.parser(task.video_status.video.url).download(task_id, download_request)


# Global instances
DOWNLOAD_TASKS = DownloadTasks()
USER_TASKS = UserTasks()