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
        # Use a longer TTL for active-download locks to avoid premature expiry on long downloads
        self.lock_ttl = max(int(self.ttl or 0), 3600)

    def _get_key(self, key: str) -> str:
        return f"{settings.REDIS_PREFIX}{key}"

    def channel_for_task(self, task_id: str) -> str:
        """Return Redis Pub/Sub channel name for a given task."""
        return self._get_key(f"events:{task_id}")

    async def publish_progress(self, task_id: str, task: DownloadTask) -> None:
        """Publish current task progress to Redis Pub/Sub channel for SSE consumers."""
        payload = {
            "task_id": task_id,
            **task.video_status.model_dump(),
        }
        await self.redis.publish(self.channel_for_task(task_id), json.dumps(payload))

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
        # Try to publish SSE update; ignore publish errors silently
        try:
            await self.publish_progress(task_id, task)
        except Exception:
            pass
        # Auto-release per-user lock if task has finished (completed, error, or done)
        try:
            status = task.video_status.status
            if status in (VideoDownloadStatus.COMPLETED, VideoDownloadStatus.ERROR, VideoDownloadStatus.DONE):
                user_id = await self.get_task_user(task_id)
                if user_id:
                    await self.release_user_active_task(user_id, task_id)
        except Exception:
            # Do not break on lock release errors
            pass

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

    # --- Per-user active download lock ---
    async def get_user_active_task(self, user_id: str) -> Optional[str]:
        """Return currently active task_id for user if exists."""
        key = self._get_key(f"active:{user_id}")
        return await self.redis.get(key)

    async def acquire_user_active_task(self, user_id: str, task_id: str) -> bool:
        """Try to acquire active-download lock for user. Returns True if acquired."""
        key = self._get_key(f"active:{user_id}")
        # NX ensures we don't override an existing lock
        result = await self.redis.set(key, task_id, ex=self.lock_ttl, nx=True)
        return bool(result)

    async def release_user_active_task(self, user_id: str, task_id: Optional[str] = None) -> None:
        """Release active-download lock for user. If task_id is provided, only release if matches."""
        key = self._get_key(f"active:{user_id}")
        if task_id is None:
            await self.redis.delete(key)
            return
        # Delete only if value matches using a small Lua script for atomicity
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            await self.redis.eval(script, 1, key, task_id)
        except Exception:
            pass

    # --- Mapping task_id -> user_id to release locks on completion ---
    async def set_task_user(self, task_id: str, user_id: str) -> None:
        key = self._get_key(f"task_user:{task_id}")
        await self.redis.set(key, user_id, ex=self.lock_ttl)

    async def get_task_user(self, task_id: str) -> Optional[str]:
        key = self._get_key(f"task_user:{task_id}")
        return await self.redis.get(key)

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