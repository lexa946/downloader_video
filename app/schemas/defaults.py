from app.schemas.main import SVideoResponse, SVideoStatus

EMPTY_VIDEO_RESPONSE = SVideoResponse(
    url="",
    title="",
    author="",
    formats=[],
    preview_url="",
    duration=0,
)



EMPTY_VIDEO_STATUS = SVideoStatus(
    task_id="",
    status="",
    description="",
    video=EMPTY_VIDEO_RESPONSE,
)