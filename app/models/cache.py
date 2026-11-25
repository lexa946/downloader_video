from typing import Optional, Dict
from redis.asyncio import Redis

from app.config import settings
from app.models.status import VideoDownloadStatus
from app.schemas.main import SVideoResponse
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
        self.lock_ttl = max(int(self.ttl or 0), 3600)

    def _get_key(self, key: str) -> str:
        return f"{settings.REDIS_PREFIX}{key}"

    def channel_for_task(self, task_id: str) -> str:
        """Return Redis Pub/Sub channel name for a given task."""
        return self._get_key(f"events:{task_id}")

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
        return DownloadTask.from_jsons(data)

    async def exist_download_task(self, task_id: str) -> bool:
        key = self._get_key(f"task:{task_id}")
        if not await self.redis.exists(key):
            return False
        return True

    async def set_download_task(self, task: DownloadTask) -> None:
        """Store download task in cache"""
        key = self._get_key(f"task:{task.id_}")
        expired_states = (VideoDownloadStatus.ERROR, VideoDownloadStatus.DONE, VideoDownloadStatus.CANCELED)
        ttl = self.ttl if task.video_status.status in expired_states else None
        saved = await self.redis.eval(
            """
            if redis.call('EXISTS', KEYS[2]) == 1 and ARGV[4] ~= 'canceled' then return 0 end
            if tonumber(ARGV[2]) > 0 then
                redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
            else
                redis.call('SET', KEYS[1], ARGV[1])
            end
            redis.call('PUBLISH', ARGV[3], ARGV[5])
            return 1
            """,
            2, key, self._get_key(f"cancel:{task.id_}"),
            task.to_jsons(), ttl or 0, self.channel_for_task(task.id_),
            task.video_status.status, task.video_status.model_dump_json(),
        )
        if not saved:
            return
        status = task.video_status.status
        if status in (VideoDownloadStatus.COMPLETED, VideoDownloadStatus.ERROR, VideoDownloadStatus.DONE,
                      VideoDownloadStatus.CANCELED):
            user_id = await self.get_task_user(task.id_)
            if user_id:
                await self.release_user_active_task(user_id, task.id_)

    async def cancel_pending_task(self, task_id: str) -> bool:
        return bool(await self.redis.eval(
            """
            local raw = redis.call('GET', KEYS[1])
            if not raw then return 0 end
            local task = cjson.decode(raw)
            local status = task.video_status
            if status.status == 'canceled' then return 1 end
            if status.status ~= 'pending' then return 0 end
            status.status = 'canceled'
            status.description = 'Загрузка отменена.'
            redis.call('SET', KEYS[2], '1', 'EX', ARGV[1])
            redis.call('SET', KEYS[1], cjson.encode(task), 'EX', ARGV[2])
            redis.call('PUBLISH', ARGV[3], cjson.encode(status))
            return 1
            """,
            2, self._get_key(f"task:{task_id}"), self._get_key(f"cancel:{task_id}"),
            self.lock_ttl, max(1, self.ttl), self.channel_for_task(task_id),
        ))

    async def is_task_canceled(self, task_id: str) -> bool:
        key = self._get_key(f"cancel:{task_id}")
        return bool(await self.redis.exists(key))

    async def delete_download_task(self, task_id: str):
        key = self._get_key(f"task:{task_id}")
        await self.redis.delete(key)

    async def get_user_active_task(self, user_id: str) -> Optional[str]:
        """Return currently active task_id for user if exists."""
        key = self._get_key(f"active:{user_id}")
        return await self.redis.get(key)

    async def acquire_user_active_task(self, user_id: str, task_id: str) -> bool:
        """Try to acquire active-download lock for user. Returns True if acquired."""
        key = self._get_key(f"active:{user_id}")

        result = await self.redis.set(key, task_id, ex=self.lock_ttl, nx=True)
        return bool(result)

    async def release_user_active_task(self, user_id: str, task_id: Optional[str] = None) -> None:
        """Release active-download lock for user. If task_id is provided, only release if matches."""
        key = self._get_key(f"active:{user_id}")
        if task_id is None:
            await self.redis.delete(key)
            return
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            await self.redis.eval(script, 1, key, task_id)
        except Exception:
            pass

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


redis_cache = RedisCache()
