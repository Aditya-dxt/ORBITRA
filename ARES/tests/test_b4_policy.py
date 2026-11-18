"""Unit tests for Policy B4 (Greedy Benefit-per-Energy Baseline)."""

import unittest

from ares.actions.models import ActionCostModel
from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.b3_joint_policy import B3JointPolicy
from ares.policies.b4_greedy_benefit_per_energy import (
    B4GreedyBenefitPerEnergyConfig,
    B4GreedyBenefitPerEnergyPolicy,
)
from ares.schemas.candidate_state import ActionType, AresCandidateState, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator


class TestB4Policy(unittest.TestCase):
    """Verifies Policy B4 (Greedy Benefit-per-Energy Baseline) behavior, formulas, and constraints."""

    def _create_candidate(
        self,
        cid: str,
        conf: float,
        unc: float,
        imp: ImportanceTier,
        x: float = 100.0,
        y: float = 100.0,
        z: float = 50.0,
    ) -> AresCandidateState:
        record = SatQueryCandidateRecord(
            schema_version="v1.0.0",
            candidate_id=cid,
            image_pair_id="pair_b4_test",
            timestamp="2026-11-17T09:00:00Z",
            predicted_change="test_feature",
            confidence=conf,
            uncertainty=unc,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=x, y_meters=y, z_meters=z)
            )
        )
        return AresCandidateState(
            detection=record,
            importance_weight=ProvenanceValue(
                value=imp.value,
                provenance=DataProvenance.ASSUMED,
                notes="B4 test assignment"
            )
        )

    def test_b4_config_defaults_and_provenance(self):
        """Verifies that all default config values are tagged ASSUMED."""
        config = B4GreedyBenefitPerEnergyConfig()
        self.assertEqual(config.recapture_uncertainty_reduction.value, 0.70)
        self.assertEqual(config.recapture_uncertainty_reduction.provenance, DataProvenance.ASSUMED)
        self.assertEqual(config.min_benefit_to_act.value, 0.05)
        self.assertEqual(config.min_benefit_to_act.provenance, DataProvenance.ASSUMED)
        self.assertEqual(config.min_cost_denominator_joules.value, 50.0)
        self.assertEqual(config.min_cost_denominator_joules.provenance, DataProvenance.ASSUMED)
        self.assertEqual(config.verification_action.value, ActionType.RECAPTURE)
        self.assertEqual(config.verification_action.provenance, DataProvenance.ASSUMED)

    def test_evaluate_benefit_formula(self):
        """Verifies marginal benefit formula: Delta B = w * u * r_recapture."""
        # p=0.70, u=0.88, w=4.0, r=0.70 -> Delta B = 4.0 * 0.88 * 0.70 = 2.464
        c = self._create_candidate("c_test", 0.70, 0.88, ImportanceTier.HIGH)
        policy = B4GreedyBenefitPerEnergyPolicy()
        benefit = policy.evaluate_benefit(c)
        self.assertAlmostEqual(benefit, 2.464, places=4)

    def test_rank_candidates_spatial_distance_ordering(self):
        """Given equal benefit, closer candidate has higher ratio (less flight energy)."""
        # Both candidates have identical w=4.0, u=0.88, p=0.70 -> same Delta B
        # c_near is 50m away; c_far is 500m away
        c_near = self._create_candidate("c_near", 0.70, 0.88, ImportanceTier.HIGH, x=50.0, y=0.0)
        c_far = self._create_candidate("c_far", 0.70, 0.88, ImportanceTier.HIGH, x=500.0, y=0.0)

        policy = B4GreedyBenefitPerEnergyPolicy()
        origin = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        ranked = policy.rank_candidates([c_far, c_near], current_pos=origin)

        # c_near must be ranked before c_far
        self.assertEqual([c.detection.candidate_id for c in ranked], ["c_near", "c_far"])
        ratio_near = policy.compute_marginal_ratio(c_near, origin)
        ratio_far = policy.compute_marginal_ratio(c_far, origin)
        self.assertGreater(ratio_near, ratio_far)

    def test_rank_candidates_benefit_ordering(self):
        """Given equal distance, higher-benefit candidate has higher ratio."""
        # Both candidates at (100, 100, 50)
        # c_high: w=4.0, u=0.88 (p=0.70)
        # c_low:  w=1.0, u=0.47 (p=0.90)
        c_high = self._create_candidate("c_high", 0.70, 0.88, ImportanceTier.HIGH, x=100.0, y=100.0)
        c_low = self._create_candidate("c_low", 0.90, 0.47, ImportanceTier.LOW, x=100.0, y=100.0)

        policy = B4GreedyBenefitPerEnergyPolicy()
        origin = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        ranked = policy.rank_candidates([c_low, c_high], current_pos=origin)

        self.assertEqual([c.detection.candidate_id for c in ranked], ["c_high", "c_low"])
        self.assertGreater(
            policy.compute_marginal_ratio(c_high, origin),
            policy.compute_marginal_ratio(c_low, origin)
        )

    def test_dynamic_spatial_reranking_as_drone_moves(self):
        """Moving current_pos changes candidate ranking dynamically."""
        # Candidate 1 at (50, 0, 50), Candidate 2 at (400, 0, 50)
        # Both have same benefit
        c1 = self._create_candidate("c1", 0.70, 0.88, ImportanceTier.HIGH, x=50.0, y=0.0)
        c2 = self._create_candidate("c2", 0.70, 0.88, ImportanceTier.HIGH, x=400.0, y=0.0)

        policy = B4GreedyBenefitPerEnergyPolicy()

        # From origin (0, 0, 0), c1 is closer (50m vs 400m) -> c1 ranked first
        ranked_from_origin = policy.rank_candidates([c1, c2], current_pos=LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0))
        self.assertEqual(ranked_from_origin[0].detection.candidate_id, "c1")

        # Once drone flies to (380, 0, 50), c2 is closer (20m vs 330m) -> c2 ranked first
        ranked_from_patrol = policy.rank_candidates([c1, c2], current_pos=LocalGridCoordinates(x_meters=380.0, y_meters=0.0, z_meters=50.0))
        self.assertEqual(ranked_from_patrol[0].detection.candidate_id, "c2")

    def test_select_action_recapture_feasible(self):
        """Selects RECAPTURE when battery supports flight transit and return reserve."""
        c = self._create_candidate("c1", 0.70, 0.88, ImportanceTier.HIGH, x=100.0, y=100.0)
        policy = B4GreedyBenefitPerEnergyPolicy()
        cost_model = ActionCostModel()
        reserve_calc = ReturnReserveCalculator()
        home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        current_pos = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

        decision = policy.select_action(
            candidate=c,
            current_pos=current_pos,
            current_battery_joules=60_000.0,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home,
        )

        self.assertEqual(decision.action, ActionType.RECAPTURE)
        self.assertTrue(decision.is_flight_action)
        self.assertTrue(decision.reserve_feasible)
        self.assertGreater(decision.estimated_cost_joules, 3000.0)
        self.assertAlmostEqual(decision.estimated_benefit, 2.464, places=3)
        self.assertIn("[B4-GREEDY]", decision.reason)

    def test_select_action_return_reserve_guardrail(self):
        """Triggers RETURN_HOME when battery cannot support flight and return reserve."""
        # Distant candidate at 3000m East, battery at only 5000 Joules
        c = self._create_candidate("c_far", 0.70, 0.88, ImportanceTier.HIGH, x=3000.0, y=0.0)
        policy = B4GreedyBenefitPerEnergyPolicy()
        cost_model = ActionCostModel()
        reserve_calc = ReturnReserveCalculator()
        home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        current_pos = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

        decision = policy.select_action(
            candidate=c,
            current_pos=current_pos,
            current_battery_joules=5000.0,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home,
        )

        self.assertEqual(decision.action, ActionType.RETURN_HOME)
        self.assertFalse(decision.reserve_feasible)
        self.assertFalse(decision.is_flight_action)
        self.assertEqual(decision.estimated_cost_joules, 0.0)
        self.assertIn("Return reserve guardrail triggered", decision.reason)

    def test_select_action_low_benefit_accepted_as_none(self):
        """Candidates with expected benefit < min_benefit_to_act are accepted as NONE."""
        # p=0.99, u=0.08, w=1.0 (Low) -> Delta B = 1.0 * 0.08 * 0.70 = 0.056 (still >= 0.05)
        # Let's use custom config with min_benefit_to_act = 0.10
        config = B4GreedyBenefitPerEnergyConfig(
            min_benefit_to_act=ProvenanceValue(value=0.10, provenance=DataProvenance.ASSUMED)
        )
        c = self._create_candidate("c_low", 0.99, 0.08, ImportanceTier.LOW, x=50.0, y=50.0)
        policy = B4GreedyBenefitPerEnergyPolicy(config=config)
        cost_model = ActionCostModel()
        reserve_calc = ReturnReserveCalculator()
        home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        current_pos = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

        decision = policy.select_action(
            candidate=c,
            current_pos=current_pos,
            current_battery_joules=60_000.0,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home,
        )

        self.assertEqual(decision.action, ActionType.NONE)
        self.assertTrue(decision.reserve_feasible)
        self.assertFalse(decision.is_flight_action)
        self.assertEqual(decision.estimated_cost_joules, 0.0)
        self.assertIn("accepted as-is", decision.reason)

    def test_single_modality_strictly_recapture(self):
        """B4 never selects STRONGER_MODEL or HUMAN_REVIEW, even when battery is tight."""
        c = self._create_candidate("c1", 0.70, 0.88, ImportanceTier.HIGH, x=500.0, y=500.0)
        policy = B4GreedyBenefitPerEnergyPolicy()
        cost_model = ActionCostModel()
        reserve_calc = ReturnReserveCalculator()
        home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

        # With adequate battery: RECAPTURE
        d1 = policy.select_action(
            candidate=c,
            current_pos=home,
            current_battery_joules=60_000.0,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home,
        )
        self.assertEqual(d1.action, ActionType.RECAPTURE)

        # With inadequate battery: triggers RETURN_HOME (does NOT fall back to STRONGER_MODEL or HUMAN_REVIEW)
        d2 = policy.select_action(
            candidate=c,
            current_pos=home,
            current_battery_joules=4000.0,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home,
        )
        self.assertEqual(d2.action, ActionType.RETURN_HOME)
        self.assertNotEqual(d2.action, ActionType.STRONGER_MODEL)
        self.assertNotEqual(d2.action, ActionType.HUMAN_REVIEW)

    def test_end_to_end_simulation(self):
        """Runs B4 in the full MissionSimulator and checks ledger and safe return."""
        c1 = self._create_candidate("c1", 0.70, 0.88, ImportanceTier.HIGH, x=80.0, y=80.0)
        c2 = self._create_candidate("c2", 0.55, 0.99, ImportanceTier.MEDIUM, x=120.0, y=100.0)
        c3 = self._create_candidate("c3", 0.90, 0.47, ImportanceTier.LOW, x=500.0, y=500.0)

        simulator = MissionSimulator(
            config=MissionSimulationConfig(initial_battery_joules=60_000.0)
        )
        policy = B4GreedyBenefitPerEnergyPolicy()
        report = simulator.run_mission(policy, [c1, c2, c3])

        self.assertTrue(report.safe_return_completed)
        self.assertGreater(report.candidates_inspected, 0)
        self.assertGreater(report.total_energy_spent_actions_joules, 0.0)
        self.assertGreater(report.final_battery_joules, 0.0)

        # Confirm all recorded actions are either RECAPTURE, NONE, or RETURN_HOME
        for rec in simulator.ledger.records:
            self.assertIn(rec.selected_action, [ActionType.RECAPTURE, ActionType.NONE, ActionType.RETURN_HOME])
            self.assertNotEqual(rec.selected_action, ActionType.STRONGER_MODEL)
            self.assertNotEqual(rec.selected_action, ActionType.HUMAN_REVIEW)

    def test_b4_vs_b3_behavioral_contrast(self):
        """Contrasts B4 (pure flight spatial dispatch) with B3 (multi-modal joint policy).

        Under tight battery budgets, B4 aborts when flight reserve fails, whereas
        B3 uses compute/human review to continue candidate processing.
        """
        # Distant candidates requiring significant flight energy
        c1 = self._create_candidate("cand_A", 0.70, 0.88, ImportanceTier.HIGH, x=150.0, y=150.0)
        c2 = self._create_candidate("cand_B", 0.55, 0.99, ImportanceTier.HIGH, x=800.0, y=800.0)
        c3 = self._create_candidate("cand_C", 0.70, 0.88, ImportanceTier.MEDIUM, x=1200.0, y=1200.0)

        # Budget of 20,000 J (adequate for 1 close flight sortie, but cannot fly to cand_B/cand_C and return)
        sim_config = MissionSimulationConfig(initial_battery_joules=20_000.0)

        # 1. Run B4 (Pure flight greedy baseline)
        sim_b4 = MissionSimulator(config=sim_config)
        policy_b4 = B4GreedyBenefitPerEnergyPolicy()
        report_b4 = sim_b4.run_mission(policy_b4, [c1, c2, c3])

        # B4 visits the close candidate, then must abort because cand_B fails flight return reserve
        self.assertTrue(report_b4.safe_return_completed)
        self.assertEqual(report_b4.candidates_inspected, 1)
        self.assertGreaterEqual(report_b4.candidates_deferred, 1)

        # 2. Run B3 (Joint multi-modal policy)
        sim_b3 = MissionSimulator(config=sim_config)
        policy_b3 = B3JointPolicy()
        report_b3 = sim_b3.run_mission(policy_b3, [c1, c2, c3])

        # B3 can process more candidates by utilizing non-flight actions (STRONGER_MODEL, HUMAN_REVIEW)
        self.assertTrue(report_b3.safe_return_completed)
        self.assertGreaterEqual(report_b3.candidates_inspected, report_b4.candidates_inspected)


if __name__ == "__main__":
    unittest.main()
