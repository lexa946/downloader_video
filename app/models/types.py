from dataclasses import dataclass
from pathlib import Path

from app.schemas.main import SVideoStatus

@dataclass
class DownloadTask:
    video_status: SVideoStatus
    filepath: Path = Path()