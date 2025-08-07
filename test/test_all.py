import pytest

from app.schemas.main import SVideoResponse


@pytest.mark.parametrize(
    "url,title,author,count_formats,preview_url,duration",[
        (
            "https://www.youtube.com/watch?v=AuT338dlaaU",
            'Ну, Tahoe! Или «О том, как Apple дизайн ломает»',
            'Rozetked',
            6,
            'https://minio.pozhar.keenetic.pro/downloader-vidio/Rozetked/Ну_Tahoe_Или_О_том_как_Apple_дизайн_ломает.png',
            1353
        ),
        (
            "https://vkvideo.ru/video-211174075_456242102",
            'Я СНЯЛА ЛИРИЛИ ЛАРИЛА в РЕАЛЬНОЙ ЖИЗНИ&#33;',
            'Double Bubble / Дабл Бабл',
            6,
            'https://sun83-2.userapi.com/impg/EsYApwe2oworF4Sb4h61XTAsoycrW5p9OIvsaw/hsq7zpK7XXY.jpg?size=800x450&quality=95&keep_aspect_ratio=1&background=000000&sign=a6b1b8e888ce00cacd5c0a3ac7ca94c5&type=video_thumb',
            1952
        ),
        # ("https://www.instagram.com/reel/DLxOyGfIzvP/?igsh=MXIwam82czRuZHRrdw==",
        #     "",
        #     "",
        #     0,
        #     "",
        #     0),
    ]
)
def test_get_all_formats(client, url:str, title: str, author: str, count_formats: int, preview_url: str, duration: str):
    response = client.post("/api/get-formats", json={"url": url})
    assert response.status_code == 200

    format_response = SVideoResponse.model_validate(response.json())
    assert format_response.title == title
    assert format_response.author == author
    assert len(format_response.formats) == count_formats
    assert format_response.preview_url == preview_url
    assert format_response.duration == duration





