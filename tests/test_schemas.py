import pytest
from pydantic import ValidationError

from gridfinity_server.schemas import (
    BinRequest,
    BaseplateRequest,
    PlateItem,
    PlateItemBinData,
    PlateItemBaseplateData,
    PlateRequest,
    Dividers,
)


class TestBinRequest:
    def test_defaults(self):
        req = BinRequest(width=2, depth=1, height=3)
        assert req.type == "hollow"
        assert req.wall_thickness == 1.2
        assert req.dividers.horizontal == 0
        assert req.dividers.vertical == 0
        assert req.magnets is False
        assert req.stackable is True
        assert req.finger_grabs is False
        assert req.label is None

    def test_solid_bin(self):
        req = BinRequest(width=1, depth=1, height=2, type="solid")
        assert req.type == "solid"

    def test_with_dividers(self):
        req = BinRequest(
            width=3, depth=2, height=4,
            dividers=Dividers(horizontal=2, vertical=1),
        )
        assert req.dividers.horizontal == 2
        assert req.dividers.vertical == 1

    def test_rejects_zero_width(self):
        with pytest.raises(ValidationError):
            BinRequest(width=0, depth=1, height=1)

    def test_rejects_oversized(self):
        with pytest.raises(ValidationError):
            BinRequest(width=11, depth=1, height=1)

    def test_rejects_thin_wall(self):
        with pytest.raises(ValidationError):
            BinRequest(width=1, depth=1, height=1, wall_thickness=0.5)

    def test_rejects_invalid_type(self):
        with pytest.raises(ValidationError):
            BinRequest(width=1, depth=1, height=1, type="magical")


class TestBaseplateRequest:
    def test_defaults(self):
        req = BaseplateRequest(grid_width=5, grid_depth=4)
        assert req.has_magnets is False

    def test_with_magnets(self):
        req = BaseplateRequest(grid_width=3, grid_depth=3, has_magnets=True)
        assert req.has_magnets is True

    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            BaseplateRequest(grid_width=0, grid_depth=1)


class TestPlateItem:
    def test_bin_data_camelcase(self):
        item = PlateItem(
            itemType="bin",
            binData={
                "width": 2, "depth": 1, "height": 3,
                "wallThickness": 1.5, "fingerGrabs": True,
            },
        )
        assert isinstance(item.bin_data, PlateItemBinData)
        assert item.bin_data.width == 2
        assert item.bin_data.wall_thickness == 1.5
        assert item.bin_data.finger_grabs is True

    def test_baseplate_data_camelcase(self):
        item = PlateItem(
            itemType="baseplate",
            binData={"gridWidth": 5, "gridDepth": 4, "hasMagnets": True},
        )
        assert isinstance(item.bin_data, PlateItemBaseplateData)
        assert item.bin_data.grid_width == 5
        assert item.bin_data.has_magnets is True


class TestPlateRequest:
    def test_basic(self):
        req = PlateRequest(
            name="test-plate",
            type="bins",
            items=[
                PlateItem(
                    x=0, y=0, rotation=0,
                    itemType="bin",
                    binData={"width": 1, "depth": 1, "height": 2},
                ),
            ],
        )
        assert len(req.items) == 1
        assert req.name == "test-plate"
