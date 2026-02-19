from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gridfinity_server.main import app, job_store


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_submit_bin_job(client):
    resp = client.post(
        "/api/jobs/bin",
        json={"width": 2, "depth": 1, "height": 3},
    )
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "jobId" in data
    assert data["status"] in ("pending", "running", "complete")


def test_submit_baseplate_job(client):
    resp = client.post(
        "/api/jobs/baseplate",
        json={"gridWidth": 3, "gridDepth": 3},
    )
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "jobId" in data


def test_submit_plate_job(client):
    resp = client.post(
        "/api/jobs/plate",
        json={
            "name": "test-plate",
            "type": "bins",
            "items": [
                {
                    "itemType": "bin",
                    "binData": {"width": 1, "depth": 1, "height": 2},
                }
            ],
        },
    )
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "jobId" in data


def test_invalid_request_returns_422(client):
    resp = client.post(
        "/api/jobs/bin",
        json={"width": 0, "depth": 1, "height": 3},
    )
    assert resp.status_code == 422


def test_job_status_not_found(client):
    resp = client.get("/api/jobs/nonexistent")
    assert resp.status_code == 404


def test_job_status_complete(client):
    job = job_store.create("bin", client_ip="test")
    job_store.set_complete(job.job_id, b"fake-stl-data", "test.stl")

    resp = client.get(f"/api/jobs/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert "resultUrl" in data


def test_job_status_failed(client):
    job = job_store.create("bin", client_ip="test")
    job_store.set_failed(job.job_id, "Something broke")

    resp = client.get(f"/api/jobs/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"] == "Something broke"


def test_job_result_not_found(client):
    resp = client.get("/api/jobs/nonexistent/result")
    assert resp.status_code == 404


def test_job_result_not_complete(client):
    job = job_store.create("bin", client_ip="test")
    resp = client.get(f"/api/jobs/{job.job_id}/result")
    assert resp.status_code == 409


def test_job_result_download(client):
    job = job_store.create("bin", client_ip="test")
    job_store.set_complete(job.job_id, b"fake-stl-data", "test.stl")

    resp = client.get(f"/api/jobs/{job.job_id}/result")
    assert resp.status_code == 200
    assert resp.content == b"fake-stl-data"
    assert "test.stl" in resp.headers.get("content-disposition", "")


def test_cache_hit_returns_200(client):
    from gridfinity_server.cache import stl_cache
    from gridfinity_server.main import _cache_key
    from gridfinity_server.schemas import BinRequest

    req = BinRequest(width=1, depth=1, height=1)
    key = _cache_key("bin", req)
    stl_cache.set(key, b"cached-stl")

    resp = client.post(
        "/api/jobs/bin",
        json={"width": 1, "depth": 1, "height": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"

    stl_cache.clear()
