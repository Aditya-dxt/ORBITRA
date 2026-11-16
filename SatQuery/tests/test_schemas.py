"""Unit tests for SatQuery candidate record schema and validation rules."""

import unittest
from pydantic import ValidationError

from SatQuery.satquery.schemas.candidate_record import (
    GeographicCoordinates,
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)


class TestCandidateRecordSchema(unittest.TestCase):
    """Verifies strict fail-fast validation, bounds, UTC timestamps, and extra field rejection."""

    def setUp(self):
        self.valid_record_dict = {
            "schema_version": "v1.0.0-provisional",
            "candidate_id": "cand_sq_levir_042_001",
            "image_pair_id": "pair_levir_test_042",
            "timestamp": "2026-11-16T10:30:00Z",
            "predicted_change": "urban_building_construction",
            "confidence": 0.842,
            "uncertainty": 0.627,
            "region": {
                "crs": "local_meter_grid",
                "local_grid": {
                    "x_meters": 245.5,
                    "y_meters": 318.0,
                    "z_meters": 50.0,
                },
                "coordinates": {
                    "center_lat": 39.902864,
                    "center_lon": 116.402875,
                    "altitude_m": 50.0,
                },
                "bbox_pixels": [128, 160, 212, 244],
            },
        }

    def test_valid_record_instantiation(self):
        record = SatQueryCandidateRecord(**self.valid_record_dict)
        self.assertEqual(record.candidate_id, "cand_sq_levir_042_001")
        self.assertEqual(record.confidence, 0.842)
        self.assertEqual(record.uncertainty, 0.627)
        self.assertEqual(record.region.local_grid.x_meters, 245.5)
        self.assertEqual(record.region.local_grid.y_meters, 318.0)
        self.assertEqual(record.region.coordinates.center_lat, 39.902864)

    def test_local_grid_is_strictly_required(self):
        """ARES requires local_grid for kinematics and energy calculation."""
        invalid_dict = self.valid_record_dict.copy()
        invalid_dict["region"] = {
            "crs": "local_meter_grid",
            "coordinates": {
                "center_lat": 39.902864,
                "center_lon": 116.402875,
                "altitude_m": 50.0,
            },
            "bbox_pixels": [128, 160, 212, 244],
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_dict)

    def test_timezone_aware_utc_timestamp_enforced(self):
        """Rejects naive timestamps without timezone information."""
        invalid_dict = self.valid_record_dict.copy()
        invalid_dict["timestamp"] = "2026-11-16T10:30:00"  # Missing Z or offset
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_dict)

        invalid_dict["timestamp"] = "invalid-date-string"
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_dict)

    def test_rejects_unknown_fields(self):
        """Enforces extra='forbid' so ARES fields or unexpected attributes are rejected."""
        invalid_dict = self.valid_record_dict.copy()
        invalid_dict["importance_weight"] = 2.0  # Owned by ARES, not SatQuery!
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_dict)

        invalid_region = self.valid_record_dict.copy()
        invalid_region["region"] = {
            "crs": "local_meter_grid",
            "local_grid": {"x_meters": 10.0, "y_meters": 20.0, "z_meters": 50.0},
            "unknown_extra": "rejected",
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_region)

    def test_confidence_and_uncertainty_bounds(self):
        invalid_conf = self.valid_record_dict.copy()
        invalid_conf["confidence"] = 1.05
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_conf)

        invalid_unc = self.valid_record_dict.copy()
        invalid_unc["uncertainty"] = -0.01
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_unc)

    def test_bbox_pixels_validation(self):
        invalid_bbox = self.valid_record_dict.copy()
        invalid_bbox["region"] = {
            "crs": "local_meter_grid",
            "local_grid": {"x_meters": 10.0, "y_meters": 20.0, "z_meters": 50.0},
            "bbox_pixels": [200, 100, 150, 120],  # xmin > xmax
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_bbox)

        invalid_len = self.valid_record_dict.copy()
        invalid_len["region"] = {
            "crs": "local_meter_grid",
            "local_grid": {"x_meters": 10.0, "y_meters": 20.0, "z_meters": 50.0},
            "bbox_pixels": [10, 20, 30],  # 3 elements instead of 4
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_len)


if __name__ == "__main__":
    unittest.main()
