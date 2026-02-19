from __future__ import annotations

import time
from unittest.mock import patch

from gridfinity_server.job_store import JobRecord, JobStatus, JobStore


def test_create_and_get():
    store = JobStore()
    job = store.create("bin", client_ip="1.2.3.4")
    assert job.status == JobStatus.PENDING
    assert job.job_type == "bin"
    assert job.client_ip == "1.2.3.4"

    fetched = store.get(job.job_id)
    assert fetched is not None
    assert fetched.job_id == job.job_id


def test_get_missing_returns_none():
    store = JobStore()
    assert store.get("nonexistent") is None


def test_lifecycle_pending_to_complete():
    store = JobStore()
    job = store.create("bin")
    assert job.status == JobStatus.PENDING

    store.set_running(job.job_id)
    fetched = store.get(job.job_id)
    assert fetched.status == JobStatus.RUNNING

    store.set_complete(job.job_id, b"stl-data", "test.stl")
    fetched = store.get(job.job_id)
    assert fetched.status == JobStatus.COMPLETE
    assert fetched.result_bytes == b"stl-data"
    assert fetched.result_filename == "test.stl"


def test_lifecycle_pending_to_failed():
    store = JobStore()
    job = store.create("bin")

    store.set_running(job.job_id)
    store.set_failed(job.job_id, "CAD error")
    fetched = store.get(job.job_id)
    assert fetched.status == JobStatus.FAILED
    assert fetched.error == "CAD error"


def test_expired_job_returns_none():
    store = JobStore(max_age_seconds=1)
    job = store.create("bin")

    with patch("gridfinity_server.job_store.time") as mock_time:
        mock_time.time.return_value = time.time() + 2
        assert store.get(job.job_id) is None


def test_active_count():
    store = JobStore()
    store.create("bin", client_ip="10.0.0.1")
    store.create("bin", client_ip="10.0.0.2")
    j3 = store.create("bin", client_ip="10.0.0.1")

    assert store.active_count() == 3
    assert store.active_count(client_ip="10.0.0.1") == 2

    store.set_complete(j3.job_id, b"data", "f.stl")
    assert store.active_count() == 2
    assert store.active_count(client_ip="10.0.0.1") == 1


def test_purge_caps_at_max():
    store = JobStore()
    store.MAX_JOBS = 5
    for _ in range(10):
        store.create("bin")

    # After purge on next create, should be capped
    store.create("bin")
    with store._lock:
        assert len(store._jobs) <= 6  # 5 cap + 1 just added before next purge


def test_set_complete_with_media_type():
    store = JobStore()
    job = store.create("plate")
    store.set_complete(job.job_id, b"zip-data", "plate.zip", "application/zip")
    fetched = store.get(job.job_id)
    assert fetched.result_media_type == "application/zip"
