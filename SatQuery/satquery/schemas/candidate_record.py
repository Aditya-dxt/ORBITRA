"""Strict Pydantic schema validation for SatQuery candidate change records.

Agreed interface schema for handoff to ARES (v1.0.0).
Enforces:
- Required local_grid for ARES transit kinematics and energy estimation
- Timezone-aware UTC ISO-8601 timestamps
- Strict rejection of unknown/extra fields (extra='forbid')
- Distinct CRS identifiers for local planar grid vs WGS84 geodetic
- Bounded confidence [0.0, 1.0] and uncertainty [0.0, 1.0]
- Valid pixel bounding box geometry [xmin, ymin, xmax, ymax]
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocalGridCoordinates(BaseModel):
    """Euclidean offset coordinates in meters relative to mission home base [0, 0, 0].
    
    Coordinate axes:
    - x_meters: Eastward distance in meters
    - y_meters: Northward distance in meters
    - z_meters: Altitude Above Ground Level (AGL) in meters
    """
    model_config = ConfigDict(extra="forbid")

    x_meters: float = Field(..., description="Eastward distance in meters from mission home base")
    y_meters: float = Field(..., description="Northward distance in meters from mission home base")
    z_meters: float = Field(default=50.0, ge=0.0, description="Altitude above ground level in meters")


class GeographicCoordinates(BaseModel):
    """WGS84 Geodetic coordinates (EPSG:4326).
    
    Labeled explicitly as an approximate transformation from local metric grid.
    """
    model_config = ConfigDict(extra="forbid")

    center_lat: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude in decimal degrees")
    center_lon: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude in decimal degrees")
    altitude_m: Optional[float] = Field(default=50.0, ge=0.0, description="Altitude in meters")


class RegionGeometry(BaseModel):
    """Spatial definition of the candidate change area."""
    model_config = ConfigDict(extra="forbid")

    crs: str = Field(
        default="local_meter_grid",
        description="Coordinate Reference System identifier (e.g. 'local_meter_grid')"
    )
    local_grid: LocalGridCoordinates = Field(
        ...,
        description="Required local meter grid coordinates for ARES energy and reserve calculations"
    )
    coordinates: Optional[GeographicCoordinates] = Field(
        default=None,
        description="Optional WGS84 geodetic approximation (EPSG:4326)"
    )
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
    """Agreed candidate change record exported by SatQuery and consumed by ARES.
    
    Contains strictly fields owned and supplied by SatQuery.
    Does NOT contain ARES-owned decision/simulation fields (importance, status, action, feasibility).
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="v1.0.0",
        description="Agreed interface schema version (v1.x)"
    )
    candidate_id: str = Field(
        ...,
        min_length=1,
        description="Unique candidate identifier (e.g. cand_sq_levir_042_001)"
    )
    image_pair_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of source bi-temporal image pair (e.g. pair_levir_test_042)"
    )
    timestamp: str = Field(
        ...,
        description="Observation timestamp in timezone-aware ISO-8601 UTC format (e.g. 2026-11-16T10:30:00Z)"
    )
    predicted_change: str = Field(
        ...,
        min_length=1,
        description="Semantic category of detected change (e.g. urban_building_construction)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated probability of genuine change p_i in [0.0, 1.0]"
    )
    uncertainty: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized binary Shannon entropy u_i in [0.0, 1.0]"
    )
    region: RegionGeometry = Field(
        ...,
        description="Spatial geometry containing local_grid and image bounding box"
    )

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if not v.startswith("v1."):
            raise ValueError(f"Unsupported schema version: '{v}'. Expected 'v1.x'")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_iso8601_timestamp(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("timestamp must be a non-empty ISO-8601 string")
        try:
            normalized = v.replace("Z", "+00:00") if v.endswith("Z") else v
            parsed = datetime.fromisoformat(normalized)
        except Exception as exc:
            raise ValueError(
                f"timestamp '{v}' is not a valid ISO-8601 string. Expected format: YYYY-MM-DDTHH:MM:SSZ"
            ) from exc

        if parsed.tzinfo is None:
            raise ValueError(
                f"timestamp '{v}' is missing timezone offset. Must be timezone-aware UTC (e.g., ending in 'Z' or '+00:00')."
            )
        return v
