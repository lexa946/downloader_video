from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from app.schemas.defaults import EMPTY_VIDEO_STATUS
from app.schemas.main import SVideoStatus

@dataclass
class DownloadTask:
    video_status: SVideoStatus
    filepath: Path = Path()



class DownloadTasks:
    tasks: dict[str, DownloadTask] = {}

    def __getitem__(self, item):
        return self.tasks.get(item, DownloadTask(EMPTY_VIDEO_STATUS))

    def __setitem__(self, key, value):
        self.tasks[key] = value

    def __contains__(self, item):
        return item in self.tasks


DOWNLOAD_TASKS = DownloadTasks()
USER_TASKS = defaultdict(lambda: deque(maxlen=5))
VIDEO_META_CACHE = {}