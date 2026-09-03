import pytest
from starlette.testclient import TestClient
from api_server import app

def test_home_page_availability():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Multiagent Router PRO" in response.text

def test_files_endpoint():
    with TestClient(app) as client:
        response = client.get("/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)
        for f in data["files"]:
            assert f.endswith(".py")

def test_websocket_communication():
    with TestClient(app).websocket_connect("/ws") as websocket:
        websocket.send_text("test")
        data = websocket.receive_text()
        assert data is not None
        assert data != ""
