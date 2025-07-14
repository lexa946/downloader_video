



def test_get_all_formats(client):
    test_url = "https://www.youtube.com/watch?v=AuT338dlaaU"
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    print()




