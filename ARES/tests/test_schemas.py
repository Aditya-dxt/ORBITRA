"""Unit tests for schema validation and candidate state tracking."""

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
    SatQueryCandidateRecord,
)


class TestSchemas(unittest.TestCase):
    """Verifies schema validation rules and field ownership boundaries."""

    def setUp(self):
        self.valid_record_dict = {
            "schema_version": "v1.0.0-provisional",
            "candidate_id": "cand_sq_001",
            "image_pair_id": "pair_01",
            "timestamp": "2026-11-16T09:00:00Z",
            "predicted_change": "built_up_increase",
            "confidence": 0.85,
            "uncertainty": 0.30,
            "region": {
                "crs": "local_meter_grid",
                "local_grid": {"x_meters": 100.0, "y_meters": 200.0, "z_meters": 50.0},
                "bbox_pixels": [10, 20, 30, 40]
            }
        }

    def test_valid_satquery_record(self):
        record = SatQueryCandidateRecord(**self.valid_record_dict)
        self.assertEqual(record.candidate_id, "cand_sq_001")
        self.assertEqual(record.confidence, 0.85)
        self.assertEqual(record.uncertainty, 0.30)
        self.assertEqual(record.region.local_grid.x_meters, 100.0)

    def test_confidence_and_uncertainty_bounds(self):
        invalid_conf = self.valid_record_dict.copy()
        invalid_conf["confidence"] = 1.2
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_conf)

        invalid_unc = self.valid_record_dict.copy()
        invalid_unc["uncertainty"] = -0.1
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_unc)

    def test_invalid_bbox_raises(self):
        invalid_bbox = self.valid_record_dict.copy()
        invalid_bbox["region"] = {
            "crs": "local_meter_grid",
            "bbox_pixels": [50, 60, 20, 30]  # xmin > xmax
        }
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_bbox)

    def test_unsupported_schema_version_raises(self):
        invalid_ver = self.valid_record_dict.copy()
        invalid_ver["schema_version"] = "v2.0.0"
        with self.assertRaises(ValidationError):
            SatQueryCandidateRecord(**invalid_ver)

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


if __name__ == "__main__":
    unittest.main()
