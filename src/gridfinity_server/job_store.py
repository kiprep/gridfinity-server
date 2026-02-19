from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class JobRecord:
    job_id: str
    job_type: str  # "bin", "baseplate", "plate"
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    result_bytes: bytes | None = None
    result_filename: str | None = None
    result_media_type: str = "application/octet-stream"
    error: str | None = None
    client_ip: str = ""


class JobStore:
    MAX_JOBS = 200

    def __init__(self, max_age_seconds: int = 3600):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._max_age = max_age_seconds

    def create(self, job_type: str, client_ip: str = "") -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(job_id=job_id, job_type=job_type, client_ip=client_ip)
        with self._lock:
            self._purge_expired()
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if self._is_expired(record):
                del self._jobs[job_id]
                return None
            return record

    def set_running(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.RUNNING

    def set_complete(
        self,
        job_id: str,
        result_bytes: bytes,
        filename: str,
        media_type: str = "application/octet-stream",
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.COMPLETE
                record.result_bytes = result_bytes
                record.result_filename = filename
                record.result_media_type = media_type

    def set_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.FAILED
                record.error = error

    def active_count(self, client_ip: str | None = None) -> int:
        with self._lock:
            active = [
                j
                for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
                and not self._is_expired(j)
            ]
            if client_ip is not None:
                active = [j for j in active if j.client_ip == client_ip]
            return len(active)

    def _is_expired(self, record: JobRecord) -> bool:
        return time.time() - record.created_at > self._max_age

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            jid
            for jid, rec in self._jobs.items()
            if now - rec.created_at > self._max_age
        ]
        for jid in expired:
            del self._jobs[jid]
        # Cap total entries
        while len(self._jobs) > self.MAX_JOBS:
            oldest = min(self._jobs, key=lambda k: self._jobs[k].created_at)
            del self._jobs[oldest]
