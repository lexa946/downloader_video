from typing import Optional

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import settings


class TaskQueue:
    def __init__(self):
        self._pool: Optional[ArqRedis] = None

    async def get(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(
                RedisSettings(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    database=settings.REDIS_DB,
                )
            )
        return self._pool


task_queue = TaskQueue()


