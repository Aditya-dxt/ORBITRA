"""Integration tests for SatQuery pipeline and cross-module ARES compatibility."""

import json
import os
import sys
import unittest

from SatQuery.satquery.pipeline import SatQueryPipeline, run_pipeline_demo
from SatQuery.satquery.schemas.candidate_record import SatQueryCandidateRecord

# Check ARES import capability
ARES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ARES"))
if ARES_PATH not in sys.path:
    sys.path.insert(0, ARES_PATH)

try:
    from ares.schemas.satquery_record import SatQueryCandidateRecord as AresCandidateRecord
    from ares.schemas.candidate_state import AresCandidateState
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False


class TestPipelineAndAresCompatibility(unittest.TestCase):
    """Verifies end-to-end pipeline export and direct loading into ARES."""

    def test_pipeline_demo_runs_and_exports_valid_records(self):
        export_path = os.path.join(os.path.dirname(__file__), "test_export.json")
        try:
            results = run_pipeline_demo(output_json=export_path)
            self.assertGreater(len(results["candidates"]), 0)
            self.assertTrue(os.path.exists(export_path))

            # Inspect exported file
            with open(export_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertIsInstance(data, list)
            self.assertEqual(len(data), len(results["candidates"]))

            # Verify SatQuery schema validation
            for record_dict in data:
                record = SatQueryCandidateRecord(**record_dict)
                self.assertTrue(record.candidate_id.startswith("cand_sq_"))
                self.assertIsNotNone(record.region.local_grid)
        finally:
            if os.path.exists(export_path):
                os.remove(export_path)

    @unittest.skipUnless(ARES_AVAILABLE, "ARES package not found in repository root")
    def test_ares_direct_loading_and_state_wrapping(self):
        """Ensures ARES can ingest SatQuery exports directly without manual edits."""
        export_path = os.path.join(os.path.dirname(__file__), "..", "exports", "sample_candidates.json")
        self.assertTrue(os.path.exists(export_path), f"Expected export at {export_path}")

        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertGreater(len(data), 0)
        ares_states = []

        for record_dict in data:
            # 1. Direct validation via ARES SatQueryCandidateRecord
            ares_record = AresCandidateRecord(**record_dict)
            self.assertEqual(ares_record.candidate_id, record_dict["candidate_id"])

            # 2. Wrapping in AresCandidateState
            state = AresCandidateState(detection=ares_record)
            self.assertEqual(state.status.value, "PENDING")
            self.assertIsNotNone(state.importance_weight)
            ares_states.append(state)

        self.assertEqual(len(ares_states), len(data))

    @unittest.skipUnless(ARES_AVAILABLE, "ARES package not found in repository root")
    def test_end_to_end_integration_example_runs(self):
        """Tests that SatQuery/examples/end_to_end_integration.py runs successfully."""
        from SatQuery.examples.end_to_end_integration import run_integration
        sample_export = os.path.join(os.path.dirname(__file__), "..", "exports", "sample_candidates.json")
        res = run_integration(candidates_json_path=sample_export, policy_name="B3", battery_wh=20.83)
        self.assertTrue(res["report"].safe_return_completed)
        self.assertGreater(len(res["decisions"]), 0)

    def test_vision_evaluation_suite_runs(self):
        """Verifies that the comprehensive evaluation runner completes and produces valid metrics."""
        from SatQuery.examples.evaluate_vision_pipeline import run_comprehensive_evaluation
        report = run_comprehensive_evaluation()
        self.assertIn("aggregate_pixel_metrics", report)
        self.assertGreater(report["aggregate_pixel_metrics"]["precision"], 0.70)
        self.assertGreater(report["aggregate_pixel_metrics"]["f1_score"], 0.50)
        self.assertIn("failure_taxonomy", report)
        self.assertGreater(len(report["failure_taxonomy"]), 0)


if __name__ == "__main__":
    unittest.main()
