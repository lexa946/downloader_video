from fastapi import HTTPException

from app.models.services import VideoServicesManager, VkVideoService, YoutubeVideoService, InstagramVideoService



def test_get_video_source_youtube():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert VideoServicesManager.get_service(url) is YoutubeVideoService

def test_get_video_source_instagram():
    url = "https://www.instagram.com/reel/abc123/"
    assert VideoServicesManager.get_service(url) is InstagramVideoService

def test_get_video_source_vk():
    url = "https://vkvideo.ru/video123456_654321"
    assert VideoServicesManager.get_service(url) is VkVideoService

def test_get_video_source_unknown():
    url = "https://example.com/video"
    try:
        service = VideoServicesManager.get_service(url)
        raise ValueError("Unknown video service " + str(service))
    except HTTPException:
        ...