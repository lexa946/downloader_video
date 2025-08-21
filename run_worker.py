from arq.worker import run_worker
from app.worker import WorkerSettings


if __name__ == "__main__":
    print("🚀 Воркер запущен локально")
    print(f"Redis: {WorkerSettings.redis_settings.host}:{WorkerSettings.redis_settings.port}")
    print("Ожидаем задачи...")

    try:
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        print("\n⏹️ Останавливаем воркер...")
