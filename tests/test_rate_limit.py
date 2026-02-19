from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from gridfinity_server.config import ServerConfig
from gridfinity_server.job_store import JobStore
from gridfinity_server.rate_limit import RateLimitMiddleware

# Minimal FastAPI app for testing the middleware in isolation
from fastapi import FastAPI


def _make_app(
    per_ip_per_minute: int = 3,
    daily_total: int = 100,
    concurrent_jobs: int = 10,
    enabled: bool = True,
) -> FastAPI:
    config = ServerConfig(
        worker_pool_size=1,
        rate_limit_enabled=enabled,
        rate_limit_per_ip_per_minute=per_ip_per_minute,
        rate_limit_concurrent_jobs=concurrent_jobs,
        rate_limit_daily_total=daily_total,
        job_max_age_seconds=3600,
    )
    job_store = JobStore()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config, job_store=job_store)

    @app.post("/api/jobs/bin")
    async def submit_job():
        return {"status": "ok"}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_rate_limit_per_ip():
    app = _make_app(per_ip_per_minute=3)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(3):
            resp = await client.post("/api/jobs/bin")
            assert resp.status_code == 200

        resp = await client.post("/api/jobs/bin")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_rate_limit_daily():
    app = _make_app(daily_total=2, per_ip_per_minute=100)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(2):
            resp = await client.post("/api/jobs/bin")
            assert resp.status_code == 200

        resp = await client.post("/api/jobs/bin")
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_disabled():
    app = _make_app(per_ip_per_minute=1, enabled=False)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(5):
            resp = await client.post("/api/jobs/bin")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_skips_non_post():
    app = _make_app(per_ip_per_minute=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # GET requests should not be rate limited
        for _ in range(5):
            resp = await client.get("/api/health")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_concurrent_jobs():
    config = ServerConfig(
        worker_pool_size=1,
        rate_limit_enabled=True,
        rate_limit_per_ip_per_minute=100,
        rate_limit_concurrent_jobs=2,
        rate_limit_daily_total=500,
        job_max_age_seconds=3600,
    )
    job_store = JobStore()
    # Pre-fill active jobs
    job_store.create("bin", client_ip="other")
    job_store.create("bin", client_ip="other")

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, config=config, job_store=job_store)

    @app.post("/api/jobs/bin")
    async def submit_job():
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/jobs/bin")
        assert resp.status_code == 429
