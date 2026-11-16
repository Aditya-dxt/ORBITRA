"""Provisional schema validation for SatQuery candidate change records.

Strictly encapsulates fields supplied by the SatQuery engine.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class LocalGridCoordinates(BaseModel):
    """Euclidean offset coordinates in meters relative to mission home base [0, 0, 0]."""
    x_meters: float = Field(..., description="Eastward distance in meters")
    y_meters: float = Field(..., description="Northward distance in meters")
    z_meters: float = Field(default=50.0, ge=0.0, description="Altitude above ground level in meters")


class GeographicCoordinates(BaseModel):
    """WGS84 Geodetic coordinates."""
    center_lat: float = Field(..., ge=-90.0, le=90.0)
    center_lon: float = Field(..., ge=-180.0, le=180.0)
    altitude_m: Optional[float] = Field(default=50.0, ge=0.0)


class RegionGeometry(BaseModel):
    """Spatial definition of the candidate change area."""
    crs: str = Field(default="local_meter_grid", description="Coordinate Reference System identifier")
    local_grid: Optional[LocalGridCoordinates] = None
    coordinates: Optional[GeographicCoordinates] = None
    bbox_pixels: Optional[List[int]] = Field(
        default=None,
        description="Bounding box in image pixel space [xmin, ymin, xmax, ymax]"
    )

    @field_validator("bbox_pixels")
    @classmethod
    def validate_bbox(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is not None:
            if len(v) != 4:
                raise ValueError("bbox_pixels must contain exactly 4 integers [xmin, ymin, xmax, ymax]")
            if v[0] > v[2] or v[1] > v[3]:
                raise ValueError("bbox_pixels must satisfy xmin <= xmax and ymin <= ymax")
        return v


class SatQueryCandidateRecord(BaseModel):
    """Provisional candidate record exported by SatQuery and consumed by ARES.
    
    Contains ONLY fields owned and supplied by SatQuery.
    """
    schema_version: str = Field(
        default="v1.0.0-provisional",
        description="Agreed interface schema version"
    )
    candidate_id: str = Field(..., min_length=1, description="Unique candidate ID")
    image_pair_id: str = Field(..., min_length=1, description="Identifier of the source image pair")
    timestamp: str = Field(..., description="Detection timestamp in ISO-8601 format")
    predicted_change: str = Field(..., min_length=1, description="Semantic classification of detected change")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence score [0.0, 1.0]")
    uncertainty: float = Field(..., ge=0.0, le=1.0, description="Model uncertainty estimate [0.0, 1.0]")
    region: RegionGeometry = Field(..., description="Spatial region and coordinates")

    @field_validator("schema_version")
    @classmethod
    def validate_schema(cls, v: str) -> str:
        if not v.startswith("v1."):
            raise ValueError(f"Unsupported schema version: {v}. Expected v1.x")
        return v
