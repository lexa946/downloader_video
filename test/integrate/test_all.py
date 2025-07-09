import pytest
from fastapi.testclient import TestClient


from app.main import app
@pytest.fixture(scope='module')
def client():
    with TestClient(app) as client:
        yield client


def test_get_all_formats(client):
    test_url = "https://www.youtube.com/watch?v=AuT338dlaaU"
    test_data = {"url": test_url}
    response = client.get("/api/get-formats", params=test_data)
    json_ = response.json()
    print()




