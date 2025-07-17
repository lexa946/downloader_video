



def test_get_all_formats(client):
    test_url = "https://www.instagram.com/reel/DLxOyGfIzvP/?igsh=MXIwam82czRuZHRrdw=="
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    response = client.post("/api/start-download", json={
        "url": test_url,
        "video_format_id": json_['formats'][0]['video_format_id'],
        "audio_format_id": json_['formats'][0]['video_format_id'],
    })
    print()




