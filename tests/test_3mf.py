from __future__ import annotations

import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from gridfinity_server.generators import parse_stl_to_mesh
from gridfinity_server.threemf import build_3mf


# --- Minimal ASCII STL for testing ---

TINY_STL = b"""\
solid tiny
  facet normal 0 0 1
    outer loop
      vertex 0.0 0.0 0.0
      vertex 1.0 0.0 0.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 1.0 0.0 0.0
      vertex 1.0 1.0 0.0
      vertex 0.0 1.0 0.0
    endloop
  endfacet
endsolid tiny
"""


class TestParseStlToMesh:
    def test_vertex_count(self):
        verts, tris = parse_stl_to_mesh(TINY_STL)
        # 6 raw vertices, but (1,0,0) and (0,1,0) are shared → 4 unique
        assert len(verts) == 4

    def test_triangle_count(self):
        verts, tris = parse_stl_to_mesh(TINY_STL)
        assert len(tris) == 2

    def test_triangle_indices_valid(self):
        verts, tris = parse_stl_to_mesh(TINY_STL)
        for v1, v2, v3 in tris:
            assert 0 <= v1 < len(verts)
            assert 0 <= v2 < len(verts)
            assert 0 <= v3 < len(verts)

    def test_empty_stl(self):
        verts, tris = parse_stl_to_mesh(b"solid empty\nendsolid empty\n")
        assert len(verts) == 0
        assert len(tris) == 0


class TestBuild3mfStructure:
    def _make_3mf(self, **kwargs):
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        tris = [(0, 1, 2)]
        defaults = dict(
            name="test",
            meshes=[("key1", verts, tris)],
            placements=[("key1", 10.0, 20.0, 0.0)],
        )
        defaults.update(kwargs)
        return build_3mf(**defaults)

    def test_is_valid_zip(self):
        data = self._make_3mf()
        assert zipfile.is_zipfile(BytesIO(data))

    def test_contains_required_files(self):
        data = self._make_3mf()
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
            assert "[Content_Types].xml" in names
            assert "_rels/.rels" in names
            assert "3D/3dmodel.model" in names

    def test_model_xml_parses(self):
        data = self._make_3mf()
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        assert root.tag.endswith("}model") or root.tag == "model"

    def test_model_has_resources_and_build(self):
        data = self._make_3mf()
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        assert root.find("m:resources", ns) is not None
        assert root.find("m:build", ns) is not None

    def test_bed_metadata(self):
        data = self._make_3mf(bed_width_mm=220.0, bed_depth_mm=220.0)
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        metas = {m.get("name"): m.text for m in root.findall("m:metadata", ns)}
        assert metas["BedWidthMm"] == "220.0"
        assert metas["BedDepthMm"] == "220.0"


class TestBuild3mfDeduplication:
    def test_same_key_shares_object(self):
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        tris = [(0, 1, 2)]
        data = build_3mf(
            name="dedup",
            meshes=[("keyA", verts, tris), ("keyA", verts, tris)],
            placements=[("keyA", 0, 0, 0), ("keyA", 42, 0, 90)],
        )
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        objects = root.findall("m:resources/m:object", ns)
        items = root.findall("m:build/m:item", ns)
        assert len(objects) == 1
        assert len(items) == 2

    def test_different_keys_separate_objects(self):
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        tris = [(0, 1, 2)]
        data = build_3mf(
            name="separate",
            meshes=[("keyA", verts, tris), ("keyB", verts, tris)],
            placements=[("keyA", 0, 0, 0), ("keyB", 42, 0, 0)],
        )
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        objects = root.findall("m:resources/m:object", ns)
        assert len(objects) == 2


class TestBuild3mfTransform:
    def _get_transform(self, rotation_deg: float, x: float = 0, y: float = 0) -> str:
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        tris = [(0, 1, 2)]
        data = build_3mf(
            name="xform",
            meshes=[("k", verts, tris)],
            placements=[("k", x, y, rotation_deg)],
        )
        with zipfile.ZipFile(BytesIO(data)) as zf:
            model_xml = zf.read("3D/3dmodel.model")
        root = ET.fromstring(model_xml)
        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        item = root.find("m:build/m:item", ns)
        return item.get("transform")

    def test_zero_rotation(self):
        t = self._get_transform(0, x=30, y=40)
        values = [float(v) for v in t.split()]
        # Identity rotation + translation
        assert values[:9] == [1, 0, 0, 0, 1, 0, 0, 0, 1]
        assert values[9] == 30.0
        assert values[10] == 40.0
        assert values[11] == 0.0

    def test_90_degree_rotation(self):
        t = self._get_transform(90, x=100, y=50)
        values = [float(v) for v in t.split()]
        assert abs(values[0] - 0.0) < 1e-5  # cos(90)
        assert abs(values[1] - (-1.0)) < 1e-5  # -sin(90)
        assert abs(values[3] - 1.0) < 1e-5  # sin(90)
        assert abs(values[4] - 0.0) < 1e-5  # cos(90)
        assert values[9] == 100.0
        assert values[10] == 50.0


@pytest.mark.slow
class TestSync3mfEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        from gridfinity_server.main import app
        with TestClient(app) as c:
            yield c

    def test_basic_3mf(self, client):
        resp = client.post("/api/plate/3mf", json={
            "name": "test-plate",
            "items": [
                {
                    "itemType": "bin",
                    "binData": {"width": 1, "depth": 1, "height": 2},
                    "xMm": 21,
                    "yMm": 21,
                }
            ],
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "model/3mf"
        assert zipfile.is_zipfile(BytesIO(resp.content))

        with zipfile.ZipFile(BytesIO(resp.content)) as zf:
            assert "3D/3dmodel.model" in zf.namelist()
            model_xml = zf.read("3D/3dmodel.model")
            root = ET.fromstring(model_xml)
            ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
            objects = root.findall("m:resources/m:object", ns)
            assert len(objects) == 1
            verts = root.findall("m:resources/m:object/m:mesh/m:vertices/m:vertex", ns)
            assert len(verts) > 3  # real mesh has many vertices


class TestAsync3mfEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        from gridfinity_server.main import app
        with TestClient(app) as c:
            yield c

    def test_submit_returns_202(self, client):
        resp = client.post("/api/jobs/plate-3mf", json={
            "name": "async-plate",
            "items": [
                {
                    "itemType": "bin",
                    "binData": {"width": 1, "depth": 1, "height": 2},
                    "xMm": 21,
                    "yMm": 21,
                }
            ],
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "jobId" in data
        assert data["status"] == "pending"

    def test_manual_complete_and_status(self, client):
        from gridfinity_server.main import job_store
        job = job_store.create("plate-3mf", client_ip="test")
        job_store.set_complete(job.job_id, b"fake-3mf", "test.3mf", "model/3mf")

        resp = client.get(f"/api/jobs/{job.job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert "resultUrl" in data


class TestValidation3mf:
    @pytest.fixture(scope="class")
    def client(self):
        from gridfinity_server.main import app
        with TestClient(app) as c:
            yield c

    def test_empty_items_returns_422(self, client):
        resp = client.post("/api/plate/3mf", json={
            "name": "empty",
        })
        assert resp.status_code == 422

    def test_missing_bin_data_returns_422(self, client):
        resp = client.post("/api/plate/3mf", json={
            "name": "bad",
            "items": [{"itemType": "bin"}],
        })
        assert resp.status_code == 422
