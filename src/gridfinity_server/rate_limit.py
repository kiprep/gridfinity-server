from __future__ import annotations

import json
import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import ServerConfig
from .job_store import JobStore


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: ServerConfig, job_store: JobStore):
        super().__init__(app)
        self._config = config
        self._job_store = job_store
        self._lock = Lock()
        # Per-IP sliding window: ip -> list of timestamps
        self._ip_hits: dict[str, list[float]] = defaultdict(list)
        # Daily counter
        self._daily_count = 0
        self._daily_reset_at = time.time() + 86400

    async def dispatch(self, request: Request, call_next):
        if not self._config.rate_limit_enabled:
            return await call_next(request)

        # Only rate-limit POST requests to job endpoints
        if request.method != "POST" or not request.url.path.startswith("/api/jobs/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        with self._lock:
            # Reset daily counter if needed
            if now >= self._daily_reset_at:
                self._daily_count = 0
                self._daily_reset_at = now + 86400

            # Check 1: Daily total
            if self._daily_count >= self._config.rate_limit_daily_total:
                return self._too_many(
                    "Daily request limit reached", retry_after=int(self._daily_reset_at - now)
                )

            # Check 2: Per-IP per-minute
            window_start = now - 60
            hits = self._ip_hits[client_ip]
            hits[:] = [t for t in hits if t > window_start]
            if len(hits) >= self._config.rate_limit_per_ip_per_minute:
                oldest_in_window = min(hits) if hits else now
                retry_after = max(1, int(oldest_in_window + 60 - now))
                return self._too_many(
                    "Too many requests per minute", retry_after=retry_after
                )

            # Check 3: Concurrent active jobs
            active = self._job_store.active_count()
            if active >= self._config.rate_limit_concurrent_jobs:
                return self._too_many(
                    "Too many concurrent jobs", retry_after=5
                )

            # All checks passed — record this request
            hits.append(now)
            self._daily_count += 1

        return await call_next(request)

    @staticmethod
    def _too_many(detail: str, retry_after: int) -> Response:
        return Response(
            content=json.dumps({"detail": detail}),
            status_code=429,
            media_type="application/json",
            headers={"Retry-After": str(retry_after)},
        )
