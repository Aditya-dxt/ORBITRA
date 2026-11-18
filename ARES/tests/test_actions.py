"""Unit tests for action cost models and simulated outcome generators."""

import unittest

from ares.actions.models import (
    ActionCostModel,
    ActionOutcomeSimulator,
    HumanReviewCostParameters,
    RecaptureCostParameters,
    StrongerModelCostParameters,
)
from ares.energy.model import DroneEnergyModel
from ares.schemas.candidate_state import ActionType, AresCandidateState
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)


class TestActions(unittest.TestCase):
    """Verifies cost models and simulated outcomes for RECAPTURE, STRONGER_MODEL, and HUMAN_REVIEW."""

    def setUp(self):
        self.cost_model = ActionCostModel()
        self.outcome_sim = ActionOutcomeSimulator()
        self.pos_a = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        self.pos_b = LocalGridCoordinates(x_meters=240.0, y_meters=0.0, z_meters=0.0)
        
        self.record = SatQueryCandidateRecord(
            schema_version="v1.0.0",
            candidate_id="cand_test_actions",
            image_pair_id="pair_01",
            timestamp="2026-11-16T09:00:00Z",
            predicted_change="flooded_cropland",
            confidence=0.70,
            uncertainty=0.88,  # h(0.70) ≈ 0.881 — formula-consistent (agreed Shannon entropy)
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=self.pos_b
            )
        )
        self.candidate = AresCandidateState(detection=self.record)

    def test_recapture_cost_estimation(self):
        # Distance 240m at 12 m/s = 20s flight -> 20s * 180W = 3600 J flight energy
        # Hover: 10s * 220W = 2200 J
        # Capture: 450 J, Compute: 350 J, Comms: 120 J
        # Total = 3600 + 2200 + 450 + 350 + 120 = 6720 J (~1.867 Wh)
        cost = self.cost_model.estimate_cost(ActionType.RECAPTURE, self.pos_a, self.pos_b)
        self.assertEqual(cost.action_type, ActionType.RECAPTURE)
        self.assertAlmostEqual(cost.energy_cost_joules, 6720.0)
        self.assertTrue(cost.is_flight_action)
        self.assertEqual(cost.human_capacity_units, 0.0)
        self.assertEqual(cost.provenance, DataProvenance.ASSUMED)
        self.assertGreater(cost.duration_sec, 20.0)

    def test_stronger_model_cost_estimation(self):
        # Heavyweight inference: 1200 J compute + 250 J offload = 1450 J
        # Zero flight/hover energy
        cost = self.cost_model.estimate_cost(ActionType.STRONGER_MODEL, self.pos_a, self.pos_b)
        self.assertEqual(cost.action_type, ActionType.STRONGER_MODEL)
        self.assertEqual(cost.energy_cost_joules, 1450.0)
        self.assertFalse(cost.is_flight_action)
        self.assertEqual(cost.human_capacity_units, 0.0)
        self.assertEqual(cost.provenance, DataProvenance.ASSUMED)

    def test_human_review_cost_estimation(self):
        # Human review: 50 J alert packet, charges 1.0 capacity unit
        cost = self.cost_model.estimate_cost(ActionType.HUMAN_REVIEW, self.pos_a, self.pos_b)
        self.assertEqual(cost.action_type, ActionType.HUMAN_REVIEW)
        self.assertEqual(cost.energy_cost_joules, 50.0)
        self.assertFalse(cost.is_flight_action)
        self.assertEqual(cost.human_capacity_units, 1.0)
        self.assertEqual(cost.provenance, DataProvenance.ASSUMED)

    def test_recapture_outcome_simulation(self):
        outcome = self.outcome_sim.simulate_outcome(ActionType.RECAPTURE, self.candidate)
        self.assertEqual(outcome.action_type, ActionType.RECAPTURE)
        self.assertEqual(outcome.provenance, DataProvenance.SIMULATED)
        self.assertTrue(outcome.outcome_summary.startswith("[SIMULATED]"))
        # Recapture cuts uncertainty substantially
        self.assertLess(outcome.post_uncertainty, outcome.prior_uncertainty)
        self.assertGreater(outcome.delta_uncertainty, 0.0)

    def test_stronger_model_outcome_simulation(self):
        outcome = self.outcome_sim.simulate_outcome(ActionType.STRONGER_MODEL, self.candidate)
        self.assertEqual(outcome.action_type, ActionType.STRONGER_MODEL)
        self.assertEqual(outcome.provenance, DataProvenance.SIMULATED)
        self.assertLess(outcome.post_uncertainty, outcome.prior_uncertainty)

    def test_human_review_outcome_simulation(self):
        outcome = self.outcome_sim.simulate_outcome(
            ActionType.HUMAN_REVIEW,
            self.candidate,
            simulated_ground_truth_change=True
        )
        self.assertEqual(outcome.action_type, ActionType.HUMAN_REVIEW)
        self.assertEqual(outcome.provenance, DataProvenance.SIMULATED)
        # Human review resolves uncertainty to near zero
        self.assertLessEqual(outcome.post_uncertainty, 0.05)
        self.assertEqual(outcome.post_confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
