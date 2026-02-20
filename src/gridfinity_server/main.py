from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .cache import stl_cache
from .config import load_config
from .generators import (
    generate_baseplate_stl,
    generate_bin_stl,
    baseplate_filename,
    bin_filename,
    parse_stl_to_mesh,
)
from .job_store import JobStore, JobStatus
from .rate_limit import RateLimitMiddleware
from .schemas import (
    BaseplateRequest,
    BinRequest,
    HealthResponse,
    JobStatusResponse,
    JobSubmitResponse,
    Plate3MFRequest,
    PlateItemBaseplateData,
    PlateItemBinData,
    PlateRequest,
)
from .threemf import build_3mf
from .worker import WorkerPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()
job_store = JobStore(max_age_seconds=config.job_max_age_seconds)
worker_pool = WorkerPool(config, job_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_pool.start()
    yield
    worker_pool.shutdown()


app = FastAPI(title="Gridfinity STL Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(RateLimitMiddleware, config=config, job_store=job_store)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://kiprep.github.io",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Existing sync endpoints (unchanged) ---


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(version=app.version)


@app.post("/api/bin/stl")
async def generate_bin(req: BinRequest):
    cache_key = _cache_key("bin", req)
    stl_bytes = stl_cache.get(cache_key)
    if stl_bytes is None:
        stl_bytes = generate_bin_stl(req)
        stl_cache.set(cache_key, stl_bytes)

    fname = bin_filename(req)
    return Response(
        content=stl_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/baseplate/stl")
async def generate_baseplate(req: BaseplateRequest):
    cache_key = _cache_key("baseplate", req)
    stl_bytes = stl_cache.get(cache_key)
    if stl_bytes is None:
        stl_bytes = generate_baseplate_stl(req)
        stl_cache.set(cache_key, stl_bytes)

    fname = baseplate_filename(req)
    return Response(
        content=stl_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/plate/stl")
async def generate_plate(req: PlateRequest):
    """Generate a ZIP of STL files for all items on a build plate."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(req.items):
            if item.bin_data is None:
                continue

            if isinstance(item.bin_data, PlateItemBinData):
                bin_req = BinRequest(
                    width=item.bin_data.width,
                    depth=item.bin_data.depth,
                    height=item.bin_data.height,
                    type=item.bin_data.type,
                    wall_thickness=item.bin_data.wall_thickness,
                    dividers=item.bin_data.dividers,
                    magnets=item.bin_data.magnets,
                    stackable=item.bin_data.stackable,
                    finger_grabs=item.bin_data.finger_grabs,
                    label=item.bin_data.label,
                )
                cache_key = _cache_key("bin", bin_req)
                stl_bytes = stl_cache.get(cache_key)
                if stl_bytes is None:
                    stl_bytes = generate_bin_stl(bin_req)
                    stl_cache.set(cache_key, stl_bytes)
                zf.writestr(bin_filename(bin_req, index=i), stl_bytes)

            elif isinstance(item.bin_data, PlateItemBaseplateData):
                bp_req = BaseplateRequest(
                    grid_width=item.bin_data.grid_width,
                    grid_depth=item.bin_data.grid_depth,
                    has_magnets=item.bin_data.has_magnets,
                )
                cache_key = _cache_key("baseplate", bp_req)
                stl_bytes = stl_cache.get(cache_key)
                if stl_bytes is None:
                    stl_bytes = generate_baseplate_stl(bp_req)
                    stl_cache.set(cache_key, stl_bytes)
                zf.writestr(baseplate_filename(bp_req), stl_bytes)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{req.name}.zip"'},
    )


@app.post("/api/plate/3mf")
async def generate_plate_3mf(req: Plate3MFRequest):
    """Generate a 3MF file with all items positioned on the build plate."""
    meshes: list[tuple[str, list, list]] = []
    placements: list[tuple[str, float, float, float]] = []
    seen_keys: set[str] = set()

    for item in req.items:
        if isinstance(item.bin_data, PlateItemBinData):
            bin_req = BinRequest(
                width=item.bin_data.width,
                depth=item.bin_data.depth,
                height=item.bin_data.height,
                type=item.bin_data.type,
                wall_thickness=item.bin_data.wall_thickness,
                dividers=item.bin_data.dividers,
                magnets=item.bin_data.magnets,
                stackable=item.bin_data.stackable,
                finger_grabs=item.bin_data.finger_grabs,
                label=item.bin_data.label,
            )
            cache_key = _cache_key("bin", bin_req)
            stl_bytes = stl_cache.get(cache_key)
            if stl_bytes is None:
                stl_bytes = generate_bin_stl(bin_req)
                stl_cache.set(cache_key, stl_bytes)
        elif isinstance(item.bin_data, PlateItemBaseplateData):
            bp_req = BaseplateRequest(
                grid_width=item.bin_data.grid_width,
                grid_depth=item.bin_data.grid_depth,
                has_magnets=item.bin_data.has_magnets,
            )
            cache_key = _cache_key("baseplate", bp_req)
            stl_bytes = stl_cache.get(cache_key)
            if stl_bytes is None:
                stl_bytes = generate_baseplate_stl(bp_req)
                stl_cache.set(cache_key, stl_bytes)
        else:
            continue

        if cache_key not in seen_keys:
            verts, tris = parse_stl_to_mesh(stl_bytes)
            meshes.append((cache_key, verts, tris))
            seen_keys.add(cache_key)

        placements.append((cache_key, item.x_mm, item.y_mm, item.rotation))

    threemf_bytes = build_3mf(
        req.name, meshes, placements, req.bed_width_mm, req.bed_depth_mm,
    )
    return Response(
        content=threemf_bytes,
        media_type="model/3mf",
        headers={"Content-Disposition": f'attachment; filename="{req.name}.3mf"'},
    )


# --- Async job endpoints ---


@app.post("/api/jobs/bin", response_model=JobSubmitResponse, status_code=202)
async def submit_bin_job(req: BinRequest, request: Request):
    cache_key = _cache_key("bin", req)
    stl_bytes = stl_cache.get(cache_key)
    if stl_bytes is not None:
        fname = bin_filename(req)
        job = job_store.create("bin", client_ip=_client_ip(request))
        job_store.set_complete(job.job_id, stl_bytes, fname)
        return JSONResponse(
            content={"jobId": job.job_id, "status": "complete"},
            status_code=200,
        )

    job = job_store.create("bin", client_ip=_client_ip(request))
    worker_pool.submit_bin(job.job_id, req.model_dump(), cache_key)
    return JSONResponse(
        content={"jobId": job.job_id, "status": "pending"},
        status_code=202,
    )


@app.post("/api/jobs/baseplate", response_model=JobSubmitResponse, status_code=202)
async def submit_baseplate_job(req: BaseplateRequest, request: Request):
    cache_key = _cache_key("baseplate", req)
    stl_bytes = stl_cache.get(cache_key)
    if stl_bytes is not None:
        fname = baseplate_filename(req)
        job = job_store.create("baseplate", client_ip=_client_ip(request))
        job_store.set_complete(job.job_id, stl_bytes, fname)
        return JSONResponse(
            content={"jobId": job.job_id, "status": "complete"},
            status_code=200,
        )

    job = job_store.create("baseplate", client_ip=_client_ip(request))
    worker_pool.submit_baseplate(job.job_id, req.model_dump(), cache_key)
    return JSONResponse(
        content={"jobId": job.job_id, "status": "pending"},
        status_code=202,
    )


@app.post("/api/jobs/plate", response_model=JobSubmitResponse, status_code=202)
async def submit_plate_job(req: PlateRequest, request: Request):
    job = job_store.create("plate", client_ip=_client_ip(request))
    worker_pool.submit_plate(job.job_id, req.model_dump())
    return JSONResponse(
        content={"jobId": job.job_id, "status": "pending"},
        status_code=202,
    )


@app.post("/api/jobs/plate-3mf", response_model=JobSubmitResponse, status_code=202)
async def submit_plate_3mf_job(req: Plate3MFRequest, request: Request):
    job = job_store.create("plate-3mf", client_ip=_client_ip(request))
    worker_pool.submit_plate_3mf(job.job_id, req.model_dump())
    return JSONResponse(
        content={"jobId": job.job_id, "status": "pending"},
        status_code=202,
    )


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        return JSONResponse(
            content={"detail": "Job not found"}, status_code=404
        )

    result: dict = {"jobId": job.job_id, "status": job.status.value}
    if job.status == JobStatus.COMPLETE:
        result["resultUrl"] = f"/api/jobs/{job.job_id}/result"
    if job.status == JobStatus.FAILED:
        result["error"] = job.error
    return JSONResponse(content=result)


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        return JSONResponse(
            content={"detail": "Job not found"}, status_code=404
        )
    if job.status != JobStatus.COMPLETE:
        return JSONResponse(
            content={"detail": "Job not complete", "status": job.status.value},
            status_code=409,
        )

    return Response(
        content=job.result_bytes,
        media_type=job.result_media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{job.result_filename}"'
        },
    )


# --- Error handler & helpers ---


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error("STL generation failed: %s", exc, exc_info=True)
    return Response(
        content=json.dumps(
            {"detail": f"STL generation failed: {exc}", "type": type(exc).__name__}
        ),
        status_code=500,
        media_type="application/json",
    )


def _cache_key(prefix: str, req) -> str:
    data = json.dumps(req.model_dump(), sort_keys=True)
    h = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"{prefix}-{h}"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
