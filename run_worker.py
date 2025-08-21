#!/usr/bin/env python3
import asyncio
import sys
import os

# Добавляем путь к app в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from arq import create_pool
from app.worker import WorkerSettings

async def main():
    # Создаем пул Redis соединений
    redis_pool = await create_pool(WorkerSettings.redis_settings)
    
    print("🚀 Воркер запущен локально")
    print(f"Redis: {WorkerSettings.redis_settings.host}:{WorkerSettings.redis_settings.port}")
    print("Ожидаем задачи...")
    
    try:
        # Держим воркер запущенным
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️ Останавливаем воркер...")
    finally:
        await redis_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
