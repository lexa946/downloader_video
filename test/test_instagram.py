



def test_get_all_formats(client):
    test_url = "https://www.instagram.com/reel/DGvSjcbtHiU/?igsh=MWJtdGdvcDZwMHNkdw=="
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    print()




