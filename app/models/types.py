from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.schemas.main import SVideoStatus, SVideoDownload

@dataclass
class DownloadTask:
    video_status: SVideoStatus
    filepath: Path = Path()
    # Original download request to allow recovery after server restarts
    download: Optional[SVideoDownload] = None