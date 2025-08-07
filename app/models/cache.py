import json
from pathlib import Path
from typing import Optional, Dict, List
from redis.asyncio import Redis

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.schemas.main import SVideoResponse, SVideoStatus
from app.models.types import DownloadTask


class RedisCache:
    def __init__(self):
        self.redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.ttl = settings.REDIS_TTL

    def _get_key(self, key: str) -> str:
        return f"{settings.REDIS_PREFIX}{key}"

    async def get_video_meta(self, url: str) -> Optional[SVideoResponse]:
        """Get video metadata from cache"""
        key = self._get_key(f"meta:{url}")
        data = await self.redis.get(key)
        if data:
            return SVideoResponse.model_validate_json(data)
        return None

    async def set_video_meta(self, url: str, meta: SVideoResponse) -> None:
        """Store video metadata in cache"""
        key = self._get_key(f"meta:{url}")
        await self.redis.set(key, meta.model_dump_json(), ex=self.ttl)

    async def get_download_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get download task from cache"""
        key = self._get_key(f"task:{task_id}")
        data = await self.redis.get(key)
        if not data:
            return None
        task_data = json.loads(data)
        return DownloadTask(
            video_status=SVideoStatus.model_validate(task_data["video_status"]),
            filepath=Path(task_data.get("filepath", ""))
        )

    async def exist_download_task(self, task_id: str) -> bool:
        key = self._get_key(f"task:{task_id}")
        if not await self.redis.exists(key):
            return False
        return True

    async def set_download_task(self, task_id: str, task: DownloadTask) -> None:
        """Store download task in cache"""
        key = self._get_key(f"task:{task_id}")
        task_data = {
            "video_status": task.video_status.model_dump(),
            "filepath": str(task.filepath)
        }
        await self.redis.set(key, json.dumps(task_data), ex=self.ttl)

    async def delete_download_task(self, task_id: str):
        key = self._get_key(f"task:{task_id}")
        await self.redis.delete(key)

    async def get_user_tasks(self, user_id: str) -> List[str]:
        """Get list of user's task IDs"""
        key = self._get_key(f"user:{user_id}")
        return await self.redis.lrange(key, 0, -1)

    async def add_user_task(self, user_id: str, task_id: str) -> None:
        """Add task ID to user's task list"""
        key = self._get_key(f"user:{user_id}")
        await self.redis.lpush(key, task_id)
        await self.redis.ltrim(key, 0, 5)  # Keep only last 6 tasks

    async def get_all_tasks(self) -> Dict[str, DownloadTask]:
        """Get all download tasks"""
        tasks = {}
        pattern = self._get_key("task:*")
        async for key in self.redis.scan_iter(pattern):
            task_id = key.split(":")[-1]
            task = await self.get_download_task(task_id)
            if task:
                tasks[task_id] = task
        return tasks


# Create global instance
redis_cache = RedisCache()