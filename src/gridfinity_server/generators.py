from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from cqgridfinity import GridfinityBox, GridfinityBaseplate

from .schemas import BinRequest, BaseplateRequest

logger = logging.getLogger(__name__)


def generate_bin_stl(req: BinRequest) -> bytes:
    """Generate STL bytes for a single Gridfinity bin."""
    logger.info("Generating bin: %dx%dx%d %s", req.width, req.depth, req.height, req.type)

    box = GridfinityBox(
        length_u=req.width,
        width_u=req.depth,
        height_u=req.height,
        holes=req.magnets,
        no_lip=not req.stackable,
        scoops=req.finger_grabs,
        labels=False,
        solid=(req.type == "solid"),
        length_div=req.dividers.vertical,
        width_div=req.dividers.horizontal,
        wall_th=req.wall_thickness,
        fillet_interior=True,
    )
    box.render()
    return _obj_to_stl_bytes(box)


def generate_baseplate_stl(req: BaseplateRequest) -> bytes:
    """Generate STL bytes for a single Gridfinity baseplate."""
    logger.info("Generating baseplate: %dx%d magnets=%s", req.grid_width, req.grid_depth, req.has_magnets)

    bp = GridfinityBaseplate(
        length_u=req.grid_width,
        width_u=req.grid_depth,
        ext_depth=2.5 if req.has_magnets else 0,
    )
    bp.render()
    return _obj_to_stl_bytes(bp)


def _obj_to_stl_bytes(obj) -> bytes:
    """Extract STL bytes from a rendered cq-gridfinity object."""
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=True) as tmp:
        obj.save_stl_file(filename=tmp.name)
        return Path(tmp.name).read_bytes()


def parse_stl_to_mesh(
    stl_bytes: bytes,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Parse ASCII STL → (vertices, triangles) with deduplication."""
    text = stl_bytes.decode("ascii", errors="replace")
    raw_verts = re.findall(r"vertex\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", text)

    vert_map: dict[tuple[float, float, float], int] = {}
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []

    tri_indices: list[int] = []
    for vx, vy, vz in raw_verts:
        key = (round(float(vx), 4), round(float(vy), 4), round(float(vz), 4))
        if key not in vert_map:
            vert_map[key] = len(vertices)
            vertices.append(key)
        tri_indices.append(vert_map[key])
        if len(tri_indices) == 3:
            triangles.append((tri_indices[0], tri_indices[1], tri_indices[2]))
            tri_indices = []

    return vertices, triangles


def bin_filename(req: BinRequest, index: int | None = None) -> str:
    """Generate a descriptive filename for a bin STL."""
    parts = [f"bin-{req.width}x{req.depth}x{req.height}", req.type]
    if req.label:
        safe = "".join(c for c in req.label if c.isalnum() or c in "-_ ")[:20].strip()
        if safe:
            parts.append(safe)
    if index is not None:
        parts.append(str(index))
    return "-".join(parts) + ".stl"


def baseplate_filename(req: BaseplateRequest) -> str:
    """Generate a descriptive filename for a baseplate STL."""
    return f"baseplate-{req.grid_width}x{req.grid_depth}.stl"
