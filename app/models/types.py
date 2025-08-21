import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.schemas.main import SVideoStatus, SVideoDownload

@dataclass
class DownloadTask:
    video_status: SVideoStatus
    filepath: Path = Path()
    download: Optional[SVideoDownload] = None

    @property
    def id_(self):
        return self.video_status.task_id

    def to_json(self) -> dict:
        return {
            "video_status": self.video_status.model_dump(),
            "filepath": str(self.filepath),
            "download": self.download.model_dump() if self.download else None,
        }

    def to_jsons(self) -> str:
        return json.dumps(self.to_json())

    @classmethod
    def from_jsons(cls, json_: str) -> "DownloadTask":
        task_data = json.loads(json_)
        return cls(
            video_status=SVideoStatus.model_validate(task_data["video_status"]),
            filepath=Path(task_data.get("filepath", "")),
            download=(SVideoDownload.model_validate(task_data["download"]) if task_data.get("download") else None),
        )