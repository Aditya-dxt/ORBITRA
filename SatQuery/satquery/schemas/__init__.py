"""Schemas module for SatQuery."""

from .candidate_record import (
    GeographicCoordinates,
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)

__all__ = [
    "GeographicCoordinates",
    "LocalGridCoordinates",
    "RegionGeometry",
    "SatQueryCandidateRecord",
]
