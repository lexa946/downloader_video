



def test_get_all_formats(client):
    test_url = "https://www.youtube.com/watch?v=AuT338dlaaU"
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    print()







def test_get_all_formats_vk(client):
    # test_url = "https://vkvideo.ru/playlist/-220754053_-2/video-220754053_456243474?pid=220754053"
    test_url = "https://vkvideo.ru/video-211174075_456242102"
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    print()





