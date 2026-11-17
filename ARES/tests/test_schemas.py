"""Unit tests for schema validation and candidate state tracking.

Updated to reflect agreed provisional interface (v1.0.0-provisional):
- confidence is calibrated P(real change) ∈ [0,1]
- uncertainty is normalized binary Shannon entropy of confidence:
      u = -[p·log₂(p) + (1-p)·log₂(1-p)]
  All test records must satisfy |u - h(confidence)| ≤ 0.15 (tolerance).
- Timestamps must carry an explicit UTC designator (Z or +00:00)
- local_grid is required inside region
- Unknown extra fields are rejected (extra='forbid')
"""

import math
import unittest
from pydantic import ValidationError

from ares.schemas.candidate_state import (
    ActionType,
    AresCandidateState,
    CandidateStatus,
    ImportanceTier,
)
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import (
    GeographicCoordinates,
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)


def _h(p: float) -> float:
    """Binary Shannon entropy: u = -[p·log2(p) + (1-p)·log2(1-p)]."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


class TestSchemas(unittest.TestCase):
    """Verifies schema validation rules and field ownership boundaries."""

    def setUp(self):
        # conf=0.85 -> h(0.85) ≈ 0.610; using u=0.61 (diff=0.000, within ±0.15)
        self.valid_record_dict = {
            "schema_version": "v1.0.0-provisional",
            "candidate_id": "cand_sq_001",
            "image_pair_id": "pair_01",
            "timestamp": "2026-11-16T09:00:00Z",
            "predicted_change": "built_up_increase",
            "confidence": 0.85,
            "uncertainty": 0.61,  # h(0.85) ≈ 0.610 — formula-consistent
            "region": {
                "crs": "local_meter_grid",
                "local_grid": {"x_meters": 100.0, "y_meters": 200.0, "z_meters": 50.0},
                "bbox_pixels": [10, 20, 30, 40]
            }
        }

    # ------------------------------------------------------------------
    # 1. Valid record round-trips correctly
    # ------------------------------------------------------------------

    def test_valid_satquery_record(self):
        record = SatQueryCandidateRecord(**self.valid_record_dict)
        self.assertEqual(record.candidate_id, "cand_sq_001")
        self.assertAlmostEqual(record.confidence, 0.85)
        self.assertAlmostEqual(record.uncertainty, 0.61)
        self.assertAlmostEqual(record.region.local_grid.x_meters, 100.0)

    # ------------------------------------------------------------------
    # 2. Confidence and uncertainty range validation
    # ------------------------------------------------------------------

    def test_confidence_and_uncertainty_bounds(self):
        invalid_conf = self.valid_record_dict.copy()
        invalid_conf["confidence"] = 1.2
        invalid_conf["uncertainty"] = 0.61  # keep uncertainty valid in isolation
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_conf)

        invalid_unc = self.valid_record_dict.copy()
        invalid_unc["uncertainty"] = -0.1
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_unc)

    # ------------------------------------------------------------------
    # 3. Bbox ordering validated
    # ------------------------------------------------------------------

    def test_invalid_bbox_raises(self):
        invalid_bbox = self.valid_record_dict.copy()
        invalid_bbox["region"] = {
            "crs": "local_meter_grid",
            "local_grid": {"x_meters": 100.0, "y_meters": 200.0},
            "bbox_pixels": [50, 60, 20, 30]  # xmin > xmax — invalid
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_bbox)

    # ------------------------------------------------------------------
    # 4. Schema version guard
    # ------------------------------------------------------------------

    def test_unsupported_schema_version_raises(self):
        invalid_ver = self.valid_record_dict.copy()
        invalid_ver["schema_version"] = "v2.0.0"
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_ver)

    # ------------------------------------------------------------------
    # 5. ARES candidate state wrapping preserves ownership separation
    # ------------------------------------------------------------------

    def test_ares_candidate_state_wrapping(self):
        record = SatQueryCandidateRecord(**self.valid_record_dict)
        state = AresCandidateState(detection=record)

        self.assertEqual(state.status, CandidateStatus.PENDING)
        self.assertEqual(state.assigned_action, ActionType.NONE)
        self.assertEqual(state.importance_weight.value, ImportanceTier.MEDIUM.value)
        self.assertEqual(state.importance_weight.provenance, DataProvenance.ASSUMED)

        state.set_importance(ImportanceTier.HIGH)
        self.assertEqual(state.importance_weight.value, 4.0)
        self.assertEqual(state.importance_weight.provenance, DataProvenance.ASSUMED)

    # ------------------------------------------------------------------
    # 6. NEW: local_grid is required — omitting it raises ValidationError
    # ------------------------------------------------------------------

    def test_missing_local_grid_raises(self):
        """local_grid is required; omitting it must raise ValidationError.

        ARES energy and kinematics calculations require local_grid for
        Euclidean distance and transit-energy estimates.
        """
        no_grid = self.valid_record_dict.copy()
        no_grid["region"] = {
            "crs": "local_meter_grid",
            "bbox_pixels": [10, 20, 30, 40]
            # local_grid intentionally absent
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**no_grid)

    # ------------------------------------------------------------------
    # 7. NEW: Timestamps without UTC designator are rejected
    # ------------------------------------------------------------------

    def test_non_utc_timestamp_raises(self):
        """Timestamps without 'Z' or '+00:00' must be rejected.

        ARES requires UTC ISO-8601 timestamps to prevent timezone-naive records
        from silently entering the pipeline (agreed with SatQuery lead).
        """
        for bad_ts in [
            "2026-11-16T09:00:00",        # no timezone designator
            "2026-11-16T09:00:00+05:30",  # IST offset — not UTC
            "2026-11-16",                  # date only
        ]:
            with self.subTest(timestamp=bad_ts):
                bad = self.valid_record_dict.copy()
                bad["timestamp"] = bad_ts
                with self.assertRaises(ValidationError):
                    SatQueryCandidateRecord(**bad)

    def test_plus00_timestamp_accepted(self):
        """'+00:00' is a valid UTC designator alongside 'Z'."""
        ok = self.valid_record_dict.copy()
        ok["timestamp"] = "2026-11-16T09:00:00+00:00"
        record = SatQueryCandidateRecord(**ok)
        self.assertIn("+00:00", record.timestamp)

    # ------------------------------------------------------------------
    # 8. NEW: Unknown extra fields are rejected (extra='forbid')
    # ------------------------------------------------------------------

    def test_unknown_field_raises(self):
        """Extra fields not in the agreed interface must be rejected.

        This prevents silent schema drift when SatQuery adds undocumented
        fields that ARES has not been updated to handle.
        """
        with_extra = self.valid_record_dict.copy()
        with_extra["importance_weight"] = 4.0  # ARES-owned field — must not appear here
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**with_extra)

        with_extra2 = self.valid_record_dict.copy()
        with_extra2["undocumented_field"] = "unexpected"
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**with_extra2)

    # ------------------------------------------------------------------
    # 9. NEW: Shannon entropy cross-check catches gross mismatches
    # ------------------------------------------------------------------

    def test_uncertainty_entropy_cross_check(self):
        """The model_validator flags uncertainty values that deviate > 0.15
        from the agreed Shannon entropy formula applied to confidence.

        Note: this is a cross-check for schema-level sanity, not a physical
        measurement.  Calibration is SatQuery's responsibility.
        """
        # conf=0.85 -> h(0.85) ≈ 0.610.  Setting uncertainty=0.99 (diff≈0.38) must fail.
        bad = self.valid_record_dict.copy()
        bad["uncertainty"] = 0.99  # far from h(0.85)≈0.610
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**bad)

    def test_valid_record_with_agreed_coordinate_example(self):
        """Sample record using the agreed coordinate convention example.

        Agreed reference (illustrative — not a surveyed ground truth):
          Home WGS84: (39.900000° N, 116.400000° E, 0 m)
          Bbox [128, 160, 212, 244] → centroid pixel (170, 202)
          Tile anchor at local (160.5 m E, 217.0 m N), GSD 0.5 m/px
          Local centroid: x=245.5 m E, y=318.0 m N, z=50 m AGL
          Geodetic centroid ≈ (39.902864° N, 116.402875° E, 50 m)
            [local flat-earth approximation, not a general georeferencing method]
        """
        # conf=0.70 -> h(0.70) ≈ 0.881; u=0.88 (diff=0.001, well within ±0.15)
        record = SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_coord_example_001",
            image_pair_id="pair_beijing_nov2026_01",
            timestamp="2026-11-17T06:00:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] built_up_increase",
            confidence=0.70,
            uncertainty=0.88,  # h(0.70) ≈ 0.881 — formula-consistent
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(
                    x_meters=245.5,   # 160.5 + 170 * 0.5 m/px (East)
                    y_meters=318.0,   # 217.0 + 202 * 0.5 m/px (North)
                    z_meters=50.0,    # 50 m AGL
                ),
                coordinates=GeographicCoordinates(
                    center_lat=39.902864,   # illustrative — local flat-earth approx
                    center_lon=116.402875,
                    altitude_m=50.0,
                ),
                bbox_pixels=[128, 160, 212, 244],
            )
        )
        self.assertAlmostEqual(record.region.local_grid.x_meters, 245.5)
        self.assertAlmostEqual(record.region.local_grid.y_meters, 318.0)
        self.assertAlmostEqual(record.region.coordinates.center_lat, 39.902864)
        self.assertAlmostEqual(record.region.coordinates.center_lon, 116.402875)


if __name__ == "__main__":
    unittest.main()
