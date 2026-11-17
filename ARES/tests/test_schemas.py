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
    # 7. NEW: Timestamps without UTC designator or malformed ISO strings rejected
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

    def test_malformed_timestamp_with_utc_suffix_raises(self):
        """Malformed strings that merely end with 'Z' or '+00:00' must be rejected.

        Verifies that timestamps are parsed as real ISO-8601 datetimes,
        not just checked with a naive string suffix.
        """
        for malformed in [
            "not-a-dateZ",                # non-datetime text with Z
            "invalid+00:00",              # non-datetime text with +00:00
            "2026-02-31T09:00:00Z",       # invalid calendar day (Feb 31)
            "2026-11-17T25:00:00Z",       # invalid hour (25)
            "2026-11-17T09:65:00Z",       # invalid minute (65)
            "T09:00:00Z",                 # time only
        ]:
            with self.subTest(timestamp=malformed):
                bad = self.valid_record_dict.copy()
                bad["timestamp"] = malformed
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
    # 9. NEW: Shannon entropy hard validation check enforces agreed semantics
    # ------------------------------------------------------------------

    def test_uncertainty_shannon_entropy_hard_validation(self):
        """Hard validation failure: raises ValidationError when |u - h(p)| > 0.15.

        Agreed formula: u = -[p*log2(p) + (1-p)*log2(1-p)].
        Tolerance: SHANNON_ENTROPY_TOLERANCE = 0.15.
        """
        # conf=0.85 -> h(0.85) ≈ 0.610.
        # u=0.99 (diff ≈ 0.380 > 0.15) must raise ValidationError.
        bad = self.valid_record_dict.copy()
        bad["confidence"] = 0.85
        bad["uncertainty"] = 0.99
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**bad)

        # u=0.77 (diff ≈ 0.160 > 0.15) must raise ValidationError.
        bad_border = self.valid_record_dict.copy()
        bad_border["confidence"] = 0.85
        bad_border["uncertainty"] = 0.77
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**bad_border)

        # u=0.75 (diff ≈ 0.140 <= 0.15) must pass.
        ok_border = self.valid_record_dict.copy()
        ok_border["confidence"] = 0.85
        ok_border["uncertainty"] = 0.75
        rec = SatQueryCandidateRecord(**ok_border)
        self.assertEqual(rec.uncertainty, 0.75)

    def test_uncertainty_entropy_boundaries(self):
        """Boundary values for Shannon entropy hard validation."""
        # p=0.5 -> h(0.5) = 1.0; u=1.0 must pass.
        rec_mid = SatQueryCandidateRecord(**{
            **self.valid_record_dict,
            "confidence": 0.5,
            "uncertainty": 1.0,
        })
        self.assertEqual(rec_mid.uncertainty, 1.0)

        # p=0.5 with u=0.5 (diff=0.5 > 0.15) must fail.
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**{
                **self.valid_record_dict,
                "confidence": 0.5,
                "uncertainty": 0.5,
            })

        # p=0.0 -> expected 0.0; u=0.0 must pass.
        rec_zero = SatQueryCandidateRecord(**{
            **self.valid_record_dict,
            "confidence": 0.0,
            "uncertainty": 0.0,
        })
        self.assertEqual(rec_zero.uncertainty, 0.0)

        # p=1.0 -> expected 0.0; u=0.0 must pass.
        rec_one = SatQueryCandidateRecord(**{
            **self.valid_record_dict,
            "confidence": 1.0,
            "uncertainty": 0.0,
        })
        self.assertEqual(rec_one.uncertainty, 0.0)

    def test_valid_record_with_agreed_coordinate_example(self):
        """Sample record using the agreed coordinate convention example.

        Agreed reference inputs:
          Home WGS84: (39.900000° N, 116.400000° E, 0 m)
          Bbox [128, 160, 212, 244] → centroid pixel (170, 202)
          Tile anchor at local (160.5 m E, 217.0 m N), GSD 0.5 m/px
          Local centroid: x = 160.5 + 170*0.5 = 245.5 m E
                          y = 217.0 + 202*0.5 = 318.0 m N
                          z = 50.0 m AGL
          Geodetic centroid (flat-earth formula with 111,320 m/deg):
              Δlat = 318.0 / 111,320 ≈ 0.002857° -> lat = 39.900000 + 0.002857 = 39.902857° N
              Δlon = 245.5 / (111,320 * cos(39.9°)) ≈ 0.002875° -> lon = 116.400000 + 0.002875 = 116.402875° E
        """
        # conf=0.70 -> h(0.70) ≈ 0.881; u=0.88 (diff=0.001, within ±0.15)
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
                    center_lat=39.902857,   # matches stated conversion formula: 39.900000 + 318.0/111320
                    center_lon=116.402875,  # matches stated conversion formula: 116.400000 + 245.5/(111320*cos(39.9°))
                    altitude_m=50.0,
                ),
                bbox_pixels=[128, 160, 212, 244],
            )
        )
        self.assertAlmostEqual(record.region.local_grid.x_meters, 245.5)
        self.assertAlmostEqual(record.region.local_grid.y_meters, 318.0)
        self.assertAlmostEqual(record.region.coordinates.center_lat, 39.902857)
        self.assertAlmostEqual(record.region.coordinates.center_lon, 116.402875)


if __name__ == "__main__":
    unittest.main()
