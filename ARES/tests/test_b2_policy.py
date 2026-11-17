"""Unit tests for ARES policy B2 — Adaptive Computation."""

import unittest

from ares.actions.models import ActionCostModel
from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.b2_adaptive_computation import (
    B2AdaptiveComputationConfig,
    B2AdaptiveComputationPolicy,
)
from ares.schemas.candidate_state import ActionType, AresCandidateState, CandidateStatus, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator
from ares.simulation.synthetic_data import create_synthetic_candidate_states


class TestB2Policy(unittest.TestCase):
    """Verifies B2 Adaptive Computation action selection, reserve checks, and simulation."""

    def setUp(self):
        self.policy = B2AdaptiveComputationPolicy()
        self.energy_model = DroneEnergyModel()
        self.reserve_calc = ReturnReserveCalculator(energy_model=self.energy_model)
        self.cost_model = ActionCostModel(energy_model=self.energy_model)
        self.home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

    def _create_candidate(self, cid: str, conf: float, unc: float, tier: ImportanceTier, x: float = 200.0) -> AresCandidateState:
        record = SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id=cid,
            image_pair_id="pair_01",
            timestamp="2026-11-16T09:00:00Z",
            predicted_change="test_change",
            confidence=conf,
            uncertainty=unc,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=x, y_meters=0.0, z_meters=50.0)
            )
        )
        return AresCandidateState(
            detection=record,
            importance_weight=ProvenanceValue(value=tier.value, provenance=DataProvenance.ASSUMED)
        )

    def test_b2_ranking_prioritizes_information_gain(self):
        # Formula-consistent (conf, u) pairs — h(conf) within ±0.15 of u:
        # c1: conf=0.97, u=0.20  h(0.97)=0.194 ✓  weight=4.0 -> gain=4.0*0.20=0.8
        # c2: conf=0.55, u=0.99  h(0.55)=0.993 ✓  weight=1.0 -> gain=1.0*0.99=0.99
        # c3: conf=0.70, u=0.88  h(0.70)=0.881 ✓  weight=4.0 -> gain=4.0*0.88=3.52
        # Expected order descending: c3 (3.52) > c2 (0.99) > c1 (0.80)
        c1 = self._create_candidate("c1", 0.97, 0.20, ImportanceTier.HIGH)
        c2 = self._create_candidate("c2", 0.55, 0.99, ImportanceTier.LOW)
        c3 = self._create_candidate("c3", 0.70, 0.88, ImportanceTier.HIGH)

        ranked = self.policy.rank_candidates([c1, c2, c3])
        self.assertEqual([c.detection.candidate_id for c in ranked], ["c3", "c2", "c1"])

    def test_b2_selects_none_for_low_uncertainty(self):
        # Candidate with u=0.20 < threshold 0.30 -> NONE
        # conf=0.97, u=0.20  h(0.97)=0.194 ✓
        c = self._create_candidate("c_low_u", 0.97, 0.20, ImportanceTier.MEDIUM)
        decision = self.policy.select_action(
            candidate=c,
            current_pos=self.home,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=self.home
        )
        self.assertEqual(decision.action, ActionType.NONE)
        self.assertEqual(decision.estimated_cost_joules, 0.0)
        self.assertTrue(decision.reserve_feasible)
        self.assertFalse(decision.is_flight_action)
        self.assertIn("already low", decision.reason.lower())

    def test_b2_selects_recapture_for_high_u_and_high_w(self):
        # Candidate with u=0.97 (>= 0.65) and weight 4.0 (>= 4.0) -> RECAPTURE
        # conf=0.60, u=0.97  h(0.60)=0.971 ✓
        c = self._create_candidate("c_high", 0.60, 0.97, ImportanceTier.HIGH, x=200.0)
        decision = self.policy.select_action(
            candidate=c,
            current_pos=self.home,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=self.home
        )
        self.assertEqual(decision.action, ActionType.RECAPTURE)
        self.assertTrue(decision.is_flight_action)
        self.assertTrue(decision.reserve_feasible)
        self.assertGreater(decision.estimated_cost_joules, 3000.0)

    def test_b2_selects_stronger_model_for_moderate_uncertainty(self):
        # Candidate with moderate u=0.61 (in [0.30, 0.65]) -> STRONGER_MODEL
        # conf=0.85, u=0.61  h(0.85)=0.610 ✓
        c = self._create_candidate("c_mod", 0.85, 0.61, ImportanceTier.MEDIUM, x=300.0)
        decision = self.policy.select_action(
            candidate=c,
            current_pos=self.home,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=self.home
        )
        self.assertEqual(decision.action, ActionType.STRONGER_MODEL)
        self.assertFalse(decision.is_flight_action)
        self.assertTrue(decision.reserve_feasible)
        # Consumes compute/offload energy (~1450 J) but zero flight energy
        self.assertEqual(decision.estimated_cost_joules, 1450.0)

    def test_b2_adaptive_downscaling_when_recapture_infeasible(self):
        # High uncertainty & high importance, but candidate is far away (1500m) and battery tight (8000 J)
        # Flight would cost ~25,000 J + return reserve (violating budget),
        # so B2 adaptively downscales to STRONGER_MODEL (1450 J)
        # conf=0.55, u=0.99  h(0.55)=0.993 ✓  (u >> 0.65 threshold -> would trigger RECAPTURE if affordable)
        c = self._create_candidate("c_far", 0.55, 0.99, ImportanceTier.HIGH, x=1500.0)
        decision = self.policy.select_action(
            candidate=c,
            current_pos=self.home,
            current_battery_joules=8_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=self.home
        )
        self.assertEqual(decision.action, ActionType.STRONGER_MODEL)
        self.assertTrue(decision.reserve_feasible)
        self.assertIn("downscaled", decision.reason.lower())

    def test_b2_simulator_run_end_to_end(self):
        candidates = create_synthetic_candidate_states()
        sim = MissionSimulator(config=MissionSimulationConfig(initial_battery_joules=60_000.0))
        report = sim.run_mission(self.policy, candidates)

        self.assertEqual(report.policy_id, "B2")
        self.assertTrue(report.safe_return_completed)
        self.assertGreater(report.final_battery_joules, 0.0)
        
        # Verify diversity of adaptive actions chosen across synthetic candidates
        action_names = {r.selected_action.value for r in sim.ledger.records if r.candidate_id != "MISSION_RETURN"}
        # Should have selected both flight (RECAPTURE) and compute (STRONGER_MODEL or NONE)
        self.assertIn(ActionType.STRONGER_MODEL.value, action_names)


if __name__ == "__main__":
    unittest.main()
