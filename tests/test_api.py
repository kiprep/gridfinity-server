import pytest
from fastapi.testclient import TestClient

from gridfinity_server.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data


@pytest.mark.slow
class TestBinEndpoint:
    def test_basic_bin(self):
        r = client.post("/api/bin/stl", json={
            "width": 1, "depth": 1, "height": 2,
        })
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert len(r.content) > 84

    def test_bin_with_options(self):
        r = client.post("/api/bin/stl", json={
            "width": 2, "depth": 1, "height": 3,
            "type": "hollow",
            "magnets": True,
            "finger_grabs": True,
            "wall_thickness": 1.5,
        })
        assert r.status_code == 200
        assert len(r.content) > 84

    def test_invalid_bin_returns_422(self):
        r = client.post("/api/bin/stl", json={
            "width": 0, "depth": 1, "height": 1,
        })
        assert r.status_code == 422


@pytest.mark.slow
class TestBaseplateEndpoint:
    def test_basic_baseplate(self):
        r = client.post("/api/baseplate/stl", json={
            "grid_width": 3, "grid_depth": 3,
        })
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert len(r.content) > 84


@pytest.mark.slow
class TestPlateEndpoint:
    def test_plate_with_bins(self):
        r = client.post("/api/plate/stl", json={
            "name": "test-plate",
            "type": "bins",
            "items": [
                {
                    "x": 0, "y": 0, "rotation": 0,
                    "itemType": "bin",
                    "binData": {"width": 1, "depth": 1, "height": 2},
                },
                {
                    "x": 42, "y": 0, "rotation": 0,
                    "itemType": "bin",
                    "binData": {"width": 2, "depth": 1, "height": 2},
                },
            ],
        })
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert len(r.content) > 100
