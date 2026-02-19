from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class Dividers(BaseModel):
    horizontal: int = Field(0, ge=0, le=10)
    vertical: int = Field(0, ge=0, le=10)


class BinRequest(BaseModel):
    model_config = {"populate_by_name": True}

    width: int = Field(..., ge=1, le=10, description="Width in gridfinity units")
    depth: int = Field(..., ge=1, le=10, description="Depth in gridfinity units")
    height: int = Field(..., ge=1, le=20, description="Height in gridfinity units")
    type: Literal["hollow", "solid"] = "hollow"
    wall_thickness: float = Field(1.2, ge=0.8, le=3.0, alias="wallThickness")
    dividers: Dividers = Field(default_factory=Dividers)
    magnets: bool = False
    stackable: bool = True
    finger_grabs: bool = Field(False, alias="fingerGrabs")
    label: str | None = None


class BaseplateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    grid_width: int = Field(..., ge=1, le=20, alias="gridWidth")
    grid_depth: int = Field(..., ge=1, le=20, alias="gridDepth")
    has_magnets: bool = Field(False, alias="hasMagnets")


class PlateItemBinData(BaseModel):
    model_config = {"populate_by_name": True}

    width: int = Field(..., ge=1, le=10)
    depth: int = Field(..., ge=1, le=10)
    height: int = Field(..., ge=1, le=20)
    type: Literal["hollow", "solid"] = "hollow"
    wall_thickness: float = Field(1.2, ge=0.8, le=3.0, alias="wallThickness")
    dividers: Dividers = Field(default_factory=Dividers)
    magnets: bool = False
    stackable: bool = True
    finger_grabs: bool = Field(False, alias="fingerGrabs")
    label: str | None = None


class PlateItemBaseplateData(BaseModel):
    model_config = {"populate_by_name": True}

    grid_width: int = Field(..., alias="gridWidth")
    grid_depth: int = Field(..., alias="gridDepth")
    has_magnets: bool = Field(False, alias="hasMagnets")


class PlateItem(BaseModel):
    model_config = {"populate_by_name": True}

    x: float = 0
    y: float = 0
    rotation: float = 0
    item_type: Literal["bin", "baseplate"] = Field(..., alias="itemType")
    bin_data: PlateItemBinData | PlateItemBaseplateData | None = Field(
        None, alias="binData"
    )


class PlateRequest(BaseModel):
    name: str = "plate"
    type: Literal["baseplate", "bins", "reprint"] = "bins"
    items: list[PlateItem]


class PlateItem3MF(BaseModel):
    model_config = {"populate_by_name": True}

    item_type: Literal["bin", "baseplate"] = Field(..., alias="itemType")
    bin_data: PlateItemBinData | PlateItemBaseplateData = Field(..., alias="binData")
    x_mm: float = Field(0, alias="xMm")
    y_mm: float = Field(0, alias="yMm")
    rotation: float = 0


class Plate3MFRequest(BaseModel):
    model_config = {"populate_by_name": True}

    name: str = "plate"
    bed_width_mm: float | None = Field(None, alias="bedWidthMm")
    bed_depth_mm: float | None = Field(None, alias="bedDepthMm")
    items: list[PlateItem3MF]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class JobSubmitResponse(BaseModel):
    model_config = {"populate_by_name": True}

    job_id: str = Field(..., alias="jobId")
    status: str


class JobStatusResponse(BaseModel):
    model_config = {"populate_by_name": True}

    job_id: str = Field(..., alias="jobId")
    status: str
    result_url: str | None = Field(None, alias="resultUrl")
    error: str | None = None
