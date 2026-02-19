from __future__ import annotations

import io
import logging
import zipfile
from concurrent.futures import Future, ProcessPoolExecutor

from .cache import stl_cache
from .config import ServerConfig
from .job_store import JobStore

logger = logging.getLogger(__name__)


# --- Functions that run in worker processes (top-level for pickling) ---


def _generate_bin_in_worker(params: dict) -> tuple[bytes, str]:
    """Generate a single bin STL in a worker process. Returns (stl_bytes, filename)."""
    from .schemas import BinRequest
    from .generators import generate_bin_stl, bin_filename

    req = BinRequest(**params)
    stl_bytes = generate_bin_stl(req)
    fname = bin_filename(req)
    return stl_bytes, fname


def _generate_baseplate_in_worker(params: dict) -> tuple[bytes, str]:
    """Generate a single baseplate STL in a worker process. Returns (stl_bytes, filename)."""
    from .schemas import BaseplateRequest
    from .generators import generate_baseplate_stl, baseplate_filename

    req = BaseplateRequest(**params)
    stl_bytes = generate_baseplate_stl(req)
    fname = baseplate_filename(req)
    return stl_bytes, fname


def _generate_plate_in_worker(params: dict) -> tuple[bytes, str, str]:
    """Generate a ZIP of STLs in a worker process. Returns (zip_bytes, filename, media_type)."""
    from .schemas import BinRequest, BaseplateRequest
    from .generators import (
        generate_bin_stl,
        generate_baseplate_stl,
        bin_filename,
        baseplate_filename,
    )

    plate_name = params.get("name", "plate")
    items = params.get("items", [])

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(items):
            bin_data = item.get("bin_data") or item.get("binData")
            if bin_data is None:
                continue
            item_type = item.get("item_type") or item.get("itemType")

            if item_type == "bin":
                req = BinRequest(**bin_data)
                stl_bytes = generate_bin_stl(req)
                zf.writestr(bin_filename(req, index=i), stl_bytes)
            elif item_type == "baseplate":
                req = BaseplateRequest(**bin_data)
                stl_bytes = generate_baseplate_stl(req)
                zf.writestr(baseplate_filename(req), stl_bytes)

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), f"{plate_name}.zip", "application/zip"


def _generate_3mf_in_worker(params: dict) -> tuple[bytes, str, str]:
    """Generate a 3MF file in a worker process. Returns (3mf_bytes, filename, media_type)."""
    from .schemas import BinRequest, BaseplateRequest
    from .generators import generate_bin_stl, generate_baseplate_stl, parse_stl_to_mesh
    from .threemf import build_3mf
    from .main import _cache_key

    plate_name = params.get("name", "plate")
    items = params.get("items", [])
    bed_width = params.get("bed_width_mm")
    bed_depth = params.get("bed_depth_mm")

    # Generate STLs and parse to meshes
    stl_by_key: dict[str, bytes] = {}
    meshes: list[tuple[str, list, list]] = []
    placements: list[tuple[str, float, float, float]] = []

    for item in items:
        bin_data = item.get("bin_data") or item.get("binData")
        item_type = item.get("item_type") or item.get("itemType")
        x_mm = item.get("x_mm", item.get("xMm", 0))
        y_mm = item.get("y_mm", item.get("yMm", 0))
        rotation = item.get("rotation", 0)

        if item_type == "bin":
            req = BinRequest(**bin_data)
            cache_key = _cache_key("bin", req)
            if cache_key not in stl_by_key:
                stl_by_key[cache_key] = generate_bin_stl(req)
        elif item_type == "baseplate":
            req = BaseplateRequest(**bin_data)
            cache_key = _cache_key("baseplate", req)
            if cache_key not in stl_by_key:
                stl_by_key[cache_key] = generate_baseplate_stl(req)
        else:
            continue

        # Parse mesh if not already done
        if not any(m[0] == cache_key for m in meshes):
            verts, tris = parse_stl_to_mesh(stl_by_key[cache_key])
            meshes.append((cache_key, verts, tris))

        placements.append((cache_key, x_mm, y_mm, rotation))

    threemf_bytes = build_3mf(plate_name, meshes, placements, bed_width, bed_depth)
    return threemf_bytes, f"{plate_name}.3mf", "model/3mf"


class WorkerPool:
    def __init__(self, config: ServerConfig, job_store: JobStore):
        self._config = config
        self._job_store = job_store
        self._executor: ProcessPoolExecutor | None = None

    def start(self) -> None:
        self._executor = ProcessPoolExecutor(
            max_workers=self._config.worker_pool_size
        )
        logger.info(
            "Worker pool started with %d workers", self._config.worker_pool_size
        )

    def shutdown(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            logger.info("Worker pool shut down")

    def submit_bin(self, job_id: str, params: dict, cache_key: str) -> None:
        self._submit(job_id, _generate_bin_in_worker, params, cache_key)

    def submit_baseplate(self, job_id: str, params: dict, cache_key: str) -> None:
        self._submit(job_id, _generate_baseplate_in_worker, params, cache_key)

    def submit_plate(self, job_id: str, params: dict) -> None:
        self._submit(job_id, _generate_plate_in_worker, params, cache_key=None)

    def submit_plate_3mf(self, job_id: str, params: dict) -> None:
        self._submit(job_id, _generate_3mf_in_worker, params, cache_key=None)

    def _submit(self, job_id: str, fn, params: dict, cache_key: str | None) -> None:
        self._job_store.set_running(job_id)
        future: Future = self._executor.submit(fn, params)
        future.add_done_callback(
            lambda f: self._on_done(f, job_id, cache_key)
        )

    def _on_done(self, future: Future, job_id: str, cache_key: str | None) -> None:
        try:
            result = future.result()
            if len(result) == 2:
                stl_bytes, filename = result
                media_type = "application/octet-stream"
            else:
                stl_bytes, filename, media_type = result

            self._job_store.set_complete(job_id, stl_bytes, filename, media_type)

            # Populate stl_cache so sync endpoints benefit
            if cache_key is not None:
                stl_cache.set(cache_key, stl_bytes)

            logger.info("Job %s completed: %s", job_id, filename)
        except Exception as exc:
            self._job_store.set_failed(job_id, str(exc))
            logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
