import pytest

from gridfinity_server.schemas import BinRequest, BaseplateRequest
from gridfinity_server.generators import (
    generate_bin_stl,
    generate_baseplate_stl,
    bin_filename,
    baseplate_filename,
)


class TestFilenames:
    """Fast tests for filename generation."""

    def test_bin_filename_basic(self):
        req = BinRequest(width=2, depth=1, height=3)
        assert bin_filename(req) == "bin-2x1x3-hollow.stl"

    def test_bin_filename_solid(self):
        req = BinRequest(width=1, depth=1, height=2, type="solid")
        assert bin_filename(req) == "bin-1x1x2-solid.stl"

    def test_bin_filename_with_label(self):
        req = BinRequest(width=2, depth=2, height=3, label="Screws")
        assert bin_filename(req) == "bin-2x2x3-hollow-Screws.stl"

    def test_bin_filename_with_index(self):
        req = BinRequest(width=1, depth=1, height=2)
        assert bin_filename(req, index=3) == "bin-1x1x2-hollow-3.stl"

    def test_baseplate_filename(self):
        req = BaseplateRequest(grid_width=5, grid_depth=4)
        assert baseplate_filename(req) == "baseplate-5x4.stl"


@pytest.mark.slow
class TestBinGeneration:
    """Slow tests that actually generate CAD geometry."""

    def test_basic_hollow_bin(self):
        req = BinRequest(width=1, depth=1, height=2)
        stl = generate_bin_stl(req)
        assert len(stl) > 84  # binary STL minimum: 80-byte header + 4-byte count

    def test_bin_with_dividers(self):
        from gridfinity_server.schemas import Dividers
        req = BinRequest(
            width=3, depth=2, height=3,
            dividers=Dividers(horizontal=1, vertical=1),
        )
        stl = generate_bin_stl(req)
        assert len(stl) > 84

    def test_solid_bin(self):
        req = BinRequest(width=2, depth=2, height=3, type="solid")
        stl = generate_bin_stl(req)
        assert len(stl) > 84


@pytest.mark.slow
class TestBaseplateGeneration:
    def test_basic_baseplate(self):
        req = BaseplateRequest(grid_width=3, grid_depth=3)
        stl = generate_baseplate_stl(req)
        assert len(stl) > 84

    def test_baseplate_with_magnets(self):
        req = BaseplateRequest(grid_width=2, grid_depth=2, has_magnets=True)
        stl = generate_baseplate_stl(req)
        assert len(stl) > 84
