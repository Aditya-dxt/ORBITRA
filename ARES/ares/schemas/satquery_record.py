"""Provisional schema validation for SatQuery candidate change records.

Strictly encapsulates fields supplied by the SatQuery engine.

INTERFACE STATUS: v1.0.0-provisional
  Fields, semantics, and coordinate conventions below reflect the agreed
  provisional interface as of 2026-11-17 (see ARES/docs/INTERFACE_PROPOSAL.md).
  This schema remains PROVISIONAL until joint end-to-end integration with
  SatQuery is completed and both module leads sign off on v1.0.0.

OWNERSHIP RULE:
  This module validates ONLY fields that SatQuery owns and supplies.
  ARES-owned fields (importance_weight, candidate_status, assigned_action,
  reserve_feasible) are defined in ares/schemas/candidate_state.py and must
  never appear inside SatQueryCandidateRecord.

UNCERTAINTY SEMANTICS & HARD VALIDATION (agreed with SatQuery lead):
  `uncertainty` is the normalized binary Shannon entropy of `confidence`:
      u = -[ p·log₂(p) + (1-p)·log₂(1-p) ]
  where p = confidence.  Boundary values:
      u = 1.0  when p = 0.5  (maximum ambiguity)
      u → 0.0  when p → 0.0 or p → 1.0  (high certainty)
  ARES enforces this as a HARD VALIDATION CHECK: if |uncertainty - h(confidence)|
  exceeds SHANNON_ENTROPY_TOLERANCE (±0.15), validation raises a hard
  ValidationError to prevent uncalibrated or corrupt records from entering ARES.

CONFIDENCE CALIBRATION (agreed with SatQuery lead):
  `confidence` is a calibrated probability P(real change) ∈ [0, 1], produced
  by temperature scaling or Platt scaling.  ARES treats it as a calibrated
  probability but does NOT verify the calibration; that is SatQuery's
  responsibility.

COORDINATE CONVENTION (agreed):
  Mission home is local [0, 0, 0] at WGS84 (39.900000° N, 116.400000° E, 0 m).
  Local grid axes: x = East (m), y = North (m), z = Altitude AGL (m).
  `local_grid` is REQUIRED for ARES energy and kinematics calculations.
  WGS84 `coordinates` are optional supplementary metadata.
  Geodetic approximation formula (not a general georeferencing method):
      Δlat ≈ y / 111_320  (degrees)
      Δlon ≈ x / (111_320 · cos(lat_home))  (degrees)
  Worked example:
      y = 318.0 m North -> Δlat = 318.0 / 111_320 ≈ 0.002857° -> lat ≈ 39.902857° N
      x = 245.5 m East  -> Δlon = 245.5 / (111_320 · cos(39.9°)) ≈ 0.002875° -> lon ≈ 116.402875° E
  See INTERFACE_PROPOSAL.md §4 for the full worked coordinate example.
"""

from datetime import datetime, timezone
import math
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Permissible tolerance for the hard Shannon entropy validation check.
# SatQuery candidate records must satisfy |uncertainty - h(confidence)| <= SHANNON_ENTROPY_TOLERANCE.
SHANNON_ENTROPY_TOLERANCE: float = 0.15


class LocalGridCoordinates(BaseModel):
    """Euclidean offset from mission home [0, 0, 0] in meters.

    Axes (agreed convention):
      x_meters: East  (+East, −West)
      y_meters: North (+North, −South)
      z_meters: Altitude above ground level (AGL), ≥ 0
    """
    model_config = ConfigDict(extra="forbid")

    x_meters: float = Field(..., description="Eastward distance from home in meters")
    y_meters: float = Field(..., description="Northward distance from home in meters")
    z_meters: float = Field(
        default=50.0, ge=0.0,
        description="Altitude above ground level in meters"
    )


class GeographicCoordinates(BaseModel):
    """WGS84 geodetic coordinates (supplementary — not used by ARES kinematics).

    ARES energy and reserve calculations use LocalGridCoordinates exclusively.
    WGS84 coordinates are informational metadata supplied by SatQuery.
    Geodetic axis order: latitude first, then longitude (ISO 6709).
    """
    model_config = ConfigDict(extra="forbid")

    center_lat: float = Field(..., ge=-90.0, le=90.0,
                              description="WGS84 latitude in decimal degrees")
    center_lon: float = Field(..., ge=-180.0, le=180.0,
                              description="WGS84 longitude in decimal degrees")
    altitude_m: Optional[float] = Field(
        default=None, ge=0.0,
        description="Altitude in meters (optional)"
    )


class RegionGeometry(BaseModel):
    """Spatial definition of the candidate change area.

    `local_grid` is REQUIRED because ARES energy and kinematics calculations
    depend on Euclidean distances in meters from home base.

    `coordinates` (WGS84) and `bbox_pixels` are optional supplementary fields.
    """
    model_config = ConfigDict(extra="forbid")

    crs: str = Field(
        default="local_meter_grid",
        description="Coordinate Reference System identifier"
    )
    local_grid: LocalGridCoordinates = Field(
        ...,
        description=(
            "REQUIRED. Euclidean offset from mission home in meters. "
            "Used by ARES for all energy, kinematics, and reserve calculations."
        )
    )
    coordinates: Optional[GeographicCoordinates] = Field(
        default=None,
        description=(
            "Optional WGS84 geodetic centroid. Informational metadata only; "
            "ARES kinematics do not use this field."
        )
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
                raise ValueError(
                    "bbox_pixels must contain exactly 4 integers [xmin, ymin, xmax, ymax]"
                )
            if v[0] > v[2] or v[1] > v[3]:
                raise ValueError(
                    "bbox_pixels must satisfy xmin <= xmax and ymin <= ymax"
                )
        return v


class SatQueryCandidateRecord(BaseModel):
    """Provisional candidate record exported by SatQuery and consumed by ARES.

    Contains ONLY fields owned and supplied by SatQuery.
    Unknown extra fields are REJECTED (extra='forbid') to prevent silent
    schema drift between modules.

    SCHEMA VERSION: v1.0.0-provisional
      Remains provisional until joint end-to-end integration is completed.
      Both module leads must agree before promoting to v1.0.0.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="v1.0.0-provisional",
        description="Agreed interface schema version (SemVer)"
    )
    candidate_id: str = Field(
        ..., min_length=1,
        description="Unique candidate detection identifier"
    )
    image_pair_id: str = Field(
        ..., min_length=1,
        description="Identifier of the bi-temporal satellite image pair"
    )
    timestamp: str = Field(
        ...,
        description=(
            "Detection timestamp in ISO-8601 UTC format. "
            "Must include an explicit UTC timezone designator (Z or +00:00)."
        )
    )
    predicted_change: str = Field(
        ..., min_length=1,
        description="Semantic change category classified by the SatQuery vision model"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description=(
            "Calibrated probability P(real change) ∈ [0, 1]. "
            "SatQuery applies temperature scaling or Platt scaling. "
            "ARES treats this as calibrated but does NOT verify calibration."
        )
    )
    uncertainty: float = Field(
        ..., ge=0.0, le=1.0,
        description=(
            "Normalized binary Shannon entropy of confidence: "
            "u = -[p·log₂(p) + (1-p)·log₂(1-p)], where p = confidence. "
            "u=1.0 at p=0.5 (maximum ambiguity); u→0 at p→0 or p→1. "
            "ARES assumes this formula but does NOT recompute or verify it."
        )
    )
    region: RegionGeometry = Field(
        ...,
        description="Spatial region including required local_grid and optional WGS84 coordinates"
    )

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if not v.startswith("v1."):
            raise ValueError(
                f"Unsupported schema version: '{v}'. "
                f"Expected v1.x (current agreed version: v1.0.0-provisional)."
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_utc(cls, v: str) -> str:
        """Validates that timestamp is a parseable ISO-8601 UTC datetime.

        Requires an explicit UTC timezone designator ('Z' or '+00:00').
        Rejects malformed strings even if they end with 'Z' or '+00:00'.
        """
        if not isinstance(v, str):
            raise ValueError("timestamp must be an ISO-8601 string")
        stripped = v.strip()
        if not (stripped.endswith("Z") or stripped.endswith("+00:00") or stripped.endswith("-00:00")):
            raise ValueError(
                f"timestamp must be UTC ISO-8601 with explicit timezone designator "
                f"('Z' or '+00:00'). Got: '{v}'. "
                f"Example: '2026-11-17T09:00:00Z'"
            )
        try:
            dt = datetime.fromisoformat(stripped)
        except Exception as e:
            raise ValueError(
                f"Malformed ISO-8601 timestamp: '{v}'. Failed to parse datetime: {e}"
            ) from e
        if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
            raise ValueError(
                f"timestamp must represent a UTC datetime (+00:00 offset). Got: '{v}'"
            )
        return stripped

    @model_validator(mode="after")
    def validate_uncertainty_matches_shannon_entropy(self) -> "SatQueryCandidateRecord":
        """Hard validation check: enforces that candidate uncertainty matches the
        normalized binary Shannon entropy of calibrated confidence within tolerance ±0.15.

        Agreed formula:
            u = -[p·log₂(p) + (1-p)·log₂(1-p)],  where p = confidence.

        Boundary values:
            u = 1.0  when p = 0.5  (maximum ambiguity)
            u -> 0.0 when p -> 0.0 or p -> 1.0  (high certainty)

        Hard failure: raises ValueError (ValidationError) if:
            |uncertainty - expected_entropy| > SHANNON_ENTROPY_TOLERANCE (default 0.15).

        This is a hard validation check to prevent corrupt or uncalibrated
        candidate records from propagating into ARES decision and energy engines.
        """
        p = self.confidence
        u_reported = self.uncertainty

        # Avoid log(0) at boundaries
        if p <= 0.0 or p >= 1.0:
            expected = 0.0
        else:
            expected = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))

        diff = abs(u_reported - expected)
        if diff > SHANNON_ENTROPY_TOLERANCE:
            raise ValueError(
                f"Hard validation failure: candidate uncertainty={u_reported:.4f} deviates "
                f"by {diff:.4f} from the agreed normalized binary Shannon entropy of "
                f"confidence={p:.4f} (expected ≈ {expected:.4f}, tolerance ±{SHANNON_ENTROPY_TOLERANCE}). "
                f"Agreed formula: u = -[p·log₂(p) + (1-p)·log₂(1-p)]."
            )
        return self
