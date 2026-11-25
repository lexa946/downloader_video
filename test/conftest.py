import pytest
from fastapi.testclient import TestClient


from app.main import app


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as client:
        client.post("/api/cookie-consent", json={"accepted": True}).raise_for_status()
        yield client
