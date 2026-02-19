from __future__ import annotations

import math
import zipfile
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring


def build_3mf(
    name: str,
    meshes: list[tuple[str, list, list]],
    placements: list[tuple[str, float, float, float]],
    bed_width_mm: float | None = None,
    bed_depth_mm: float | None = None,
) -> bytes:
    """Build a 3MF ZIP from meshes and placements.

    Args:
        name: Model name (used in metadata).
        meshes: List of (cache_key, vertices, triangles). One entry per unique geometry.
        placements: List of (cache_key, x_mm, y_mm, rotation_deg). One per item on plate.
        bed_width_mm: Optional bed width for metadata.
        bed_depth_mm: Optional bed depth for metadata.

    Returns:
        3MF file as bytes (ZIP archive).
    """
    # Deduplicate meshes by cache_key
    key_to_object_id: dict[str, int] = {}
    objects: list[tuple[int, list, list]] = []  # (object_id, vertices, triangles)

    for cache_key, vertices, triangles in meshes:
        if cache_key not in key_to_object_id:
            obj_id = len(objects) + 1
            key_to_object_id[cache_key] = obj_id
            objects.append((obj_id, vertices, triangles))

    # Build 3D/3dmodel.model XML
    model_xml = _build_model_xml(
        name, objects, placements, key_to_object_id,
        bed_width_mm, bed_depth_mm,
    )

    # Assemble ZIP
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("3D/3dmodel.model", model_xml)

    buf.seek(0)
    return buf.getvalue()


def _build_model_xml(
    name: str,
    objects: list[tuple[int, list, list]],
    placements: list[tuple[str, float, float, float]],
    key_to_object_id: dict[str, int],
    bed_width_mm: float | None,
    bed_depth_mm: float | None,
) -> str:
    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    model = Element("model", {"unit": "millimeter", "xmlns": ns})

    # Metadata
    _add_meta(model, "Title", name)
    _add_meta(model, "Application", "Gridfinity Server")
    if bed_width_mm is not None:
        _add_meta(model, "BedWidthMm", str(bed_width_mm))
    if bed_depth_mm is not None:
        _add_meta(model, "BedDepthMm", str(bed_depth_mm))

    # Resources
    resources = SubElement(model, "resources")
    for obj_id, vertices, triangles in objects:
        obj_el = SubElement(resources, "object", {"id": str(obj_id), "type": "model"})
        mesh_el = SubElement(obj_el, "mesh")

        verts_el = SubElement(mesh_el, "vertices")
        for x, y, z in vertices:
            SubElement(verts_el, "vertex", {
                "x": f"{x:.4f}", "y": f"{y:.4f}", "z": f"{z:.4f}",
            })

        tris_el = SubElement(mesh_el, "triangles")
        for v1, v2, v3 in triangles:
            SubElement(tris_el, "triangle", {
                "v1": str(v1), "v2": str(v2), "v3": str(v3),
            })

    # Build
    build = SubElement(model, "build")
    for cache_key, x_mm, y_mm, rotation_deg in placements:
        obj_id = key_to_object_id[cache_key]
        transform = _transform_string(x_mm, y_mm, rotation_deg)
        SubElement(build, "item", {
            "objectid": str(obj_id),
            "transform": transform,
        })

    xml_decl = '<?xml version="1.0" encoding="UTF-8"?>\n'
    return xml_decl + tostring(model, encoding="unicode")


def _transform_string(x_mm: float, y_mm: float, rotation_deg: float) -> str:
    """Build 3MF affine transform: rotate around Z then translate."""
    theta = math.radians(rotation_deg)
    c = round(math.cos(theta), 6)
    s = round(math.sin(theta), 6)
    # 3MF row-major 3x4: m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32
    values = [c, -s, 0, s, c, 0, 0, 0, 1, x_mm, y_mm, 0]
    return " ".join(_fmt(v) for v in values)


def _fmt(v: float) -> str:
    """Format a float, stripping trailing zeros."""
    if v == int(v):
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _add_meta(parent: Element, name: str, value: str) -> None:
    el = SubElement(parent, "metadata", {"name": name})
    el.text = value


_CONTENT_TYPES = """\
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />
</Types>"""

_RELS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" \
Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" />
</Relationships>"""
