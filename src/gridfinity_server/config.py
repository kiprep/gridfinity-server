from __future__ import annotations

import os
import platform
from dataclasses import dataclass


def _is_mac() -> bool:
    return platform.system() == "Darwin"


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    return int(val)


@dataclass(frozen=True)
class ServerConfig:
    worker_pool_size: int
    rate_limit_enabled: bool
    rate_limit_per_ip_per_minute: int
    rate_limit_concurrent_jobs: int
    rate_limit_daily_total: int
    job_max_age_seconds: int


def load_config() -> ServerConfig:
    mac = _is_mac()
    return ServerConfig(
        worker_pool_size=_env_int("GRID_WORKER_POOL_SIZE", 2),
        rate_limit_enabled=_env_bool("GRID_RATE_LIMIT_ENABLED", not mac),
        rate_limit_per_ip_per_minute=_env_int("GRID_RATE_LIMIT_PER_IP_PER_MINUTE", 10),
        rate_limit_concurrent_jobs=_env_int("GRID_RATE_LIMIT_CONCURRENT_JOBS", 4),
        rate_limit_daily_total=_env_int("GRID_RATE_LIMIT_DAILY_TOTAL", 500),
        job_max_age_seconds=_env_int("GRID_JOB_MAX_AGE_SECONDS", 3600),
    )
