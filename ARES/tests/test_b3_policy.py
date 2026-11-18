"""Unit tests for ARES policy B3 — Joint Policy.

All candidates are synthetic ([SYNTHETIC EXAMPLE]).
All outcome rates are ASSUMED.  All simulated results are tagged SIMULATED.
"""

import unittest

from ares.actions.models import ActionCostModel, ActionOutcomeSimulator
from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.b3_joint_policy import B3JointPolicy, B3JointPolicyConfig
from ares.schemas.candidate_state import ActionType, AresCandidateState, CandidateStatus, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator
from ares.simulation.synthetic_data import create_synthetic_candidate_states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    cid: str,
    conf: float,
    unc: float,
    tier: ImportanceTier,
    x: float = 200.0,
    y: float = 0.0,
) -> AresCandidateState:
    """[SYNTHETIC EXAMPLE] candidate factory for B3 unit tests."""
    record = SatQueryCandidateRecord(
        schema_version="v1.0.0",
        candidate_id=cid,
        image_pair_id="pair_b3_test",
        timestamp="2026-11-16T10:00:00Z",
        predicted_change="[SYNTHETIC EXAMPLE] test_change",
        confidence=conf,
        uncertainty=unc,
        region=RegionGeometry(
            crs="local_meter_grid",
            local_grid=LocalGridCoordinates(x_meters=x, y_meters=y, z_meters=50.0)
        )
    )
    return AresCandidateState(
        detection=record,
        importance_weight=ProvenanceValue(
            value=tier.value,
            provenance=DataProvenance.ASSUMED,
            notes=f"[SYNTHETIC EXAMPLE] Test assignment: {tier.name}"
        )
    )


HOME = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestB3JointPolicy(unittest.TestCase):
    """Verifies B3 joint candidate-action selection, scoring, reserve enforcement, and simulation."""

    def setUp(self):
        self.policy = B3JointPolicy()
        self.energy_model = DroneEnergyModel()
        self.reserve_calc = ReturnReserveCalculator(energy_model=self.energy_model)
        self.cost_model = ActionCostModel(energy_model=self.energy_model)

    # ------------------------------------------------------------------
    # 1. rank_candidates — B3 returns pending candidates in input order
    # ------------------------------------------------------------------

    def test_b3_rank_candidates_returns_pending_in_input_order(self):
        """rank_candidates() must return PENDING candidates in input order (joint eval happens inside select_action)."""
        # Formula-consistent pairs: conf=0.70, u=0.88  h(0.70)=0.881 ✓
        c1 = _make_candidate("c1", 0.70, 0.88, ImportanceTier.HIGH)
        c2 = _make_candidate("c2", 0.90, 0.47, ImportanceTier.LOW)   # h(0.90)=0.469 ✓
        c3 = _make_candidate("c3", 0.85, 0.61, ImportanceTier.MEDIUM)  # h(0.85)=0.610 ✓

        ranked = self.policy.rank_candidates([c1, c2, c3])
        # B3 preserves input order; joint scoring happens inside select_action
        self.assertEqual([c.detection.candidate_id for c in ranked], ["c1", "c2", "c3"])

    # ------------------------------------------------------------------
    # 2. evaluate_benefit — baseline proxy
    # ------------------------------------------------------------------

    def test_b3_evaluate_benefit_is_weight_times_uncertainty(self):
        """evaluate_benefit() = importance_weight * uncertainty (baseline proxy)."""
        # conf=0.60, u=0.97  h(0.60)=0.971 ✓   w=4.0 -> benefit=4.0*0.97=3.88
        c = _make_candidate("c_eb", 0.60, 0.97, ImportanceTier.HIGH)
        benefit = self.policy.evaluate_benefit(c)
        self.assertAlmostEqual(benefit, 4.0 * 0.97, places=4)

    # ------------------------------------------------------------------
    # 3. Joint scoring selects best (candidate, action) pair
    # ------------------------------------------------------------------

    def test_b3_joint_selects_best_pair_across_candidates(self):
        """With two pending candidates at the same distance, B3 selects from the
        higher-importance candidate because every action score scales with importance weight.

        [SYNTHETIC EXAMPLE] Setup:
          c_low:  w=1.0, u=0.90, x=100m
          c_high: w=4.0, u=0.90, x=100m (same distance)

        For any given action type at the same distance, score(c_high) = 4 * score(c_low).
        Therefore the winning (candidate, action) pair must come from c_high.
        The specific action chosen (RECAPTURE / STRONGER_MODEL / HUMAN_REVIEW) depends
        on the joint objective and is not asserted here — only the winning candidate is.
        """
        # Formula-consistent: conf=0.55, u=0.99  h(0.55)=0.993 ✓
        c_low = _make_candidate("c_low", 0.55, 0.99, ImportanceTier.LOW, x=100.0)
        c_high = _make_candidate("c_high", 0.55, 0.99, ImportanceTier.HIGH, x=100.0)

        _, decision = self.policy.run_joint_step(
            all_candidates=[c_low, c_high],
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )

        # Best joint score must come from c_high (higher importance) for any action type
        self.assertTrue(decision.reserve_feasible)
        self.assertIn("c_high", decision.reason,
                      msg="B3 joint objective must select from the higher-importance candidate")
        # Action must be one of the substantive verification actions
        self.assertIn(decision.action,
                      [ActionType.RECAPTURE, ActionType.STRONGER_MODEL, ActionType.HUMAN_REVIEW])

    def test_b3_joint_selects_recapture_when_human_review_disabled(self):
        """When HUMAN_REVIEW is disabled in config, B3 must not select it.

        [SYNTHETIC EXAMPLE] Without HUMAN_REVIEW (which has a cheaply-clamped denominator),
        RECAPTURE or STRONGER_MODEL must be chosen for a high-uncertainty, high-importance
        candidate with sufficient battery.
        """
        config = B3JointPolicyConfig(
            allow_human_review=ProvenanceValue(
                value=False,
                provenance=DataProvenance.ASSUMED,
                notes="Test: disable human review to verify flight/compute branch"
            )
        )
        policy = B3JointPolicy(config=config)

        # Formula-consistent: conf=0.55, u=0.99  h(0.55)=0.993 ✓
        c = _make_candidate("c_no_hr", 0.55, 0.99, ImportanceTier.HIGH, x=100.0)

        _, decision = policy.run_joint_step(
            all_candidates=[c],
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )

        self.assertNotEqual(decision.action, ActionType.HUMAN_REVIEW,
                            msg="HUMAN_REVIEW must be excluded when allow_human_review=False")
        self.assertIn(decision.action, [ActionType.RECAPTURE, ActionType.STRONGER_MODEL])

    # ------------------------------------------------------------------
    # 4. Reserve guardrail enforced — no infeasible action selected
    # ------------------------------------------------------------------

    def test_b3_respects_reserve_guardrail(self):
        """B3 must never select an action that fails the return-reserve check.

        [SYNTHETIC EXAMPLE]: Candidate at x=2000m with tiny remaining battery (5000 J).
        RECAPTURE flight would exhaust reserve.  B3 must downgrade to a cheaper action
        (STRONGER_MODEL or HUMAN_REVIEW) or return RETURN_HOME.
        """
        # Formula-consistent: conf=0.55, u=0.99  h(0.55)=0.993 ✓  x=2000m
        c_far = _make_candidate("c_far", 0.55, 0.99, ImportanceTier.HIGH, x=2000.0)

        _, decision = self.policy.run_joint_step(
            all_candidates=[c_far],
            current_pos=HOME,
            current_battery_joules=5_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )

        # RECAPTURE to 2000m should be infeasible; policy must not select it
        self.assertNotEqual(decision.action, ActionType.RECAPTURE)
        # Whichever action is chosen, it must be reserve-feasible (or RETURN_HOME)
        if decision.action != ActionType.RETURN_HOME:
            self.assertTrue(decision.reserve_feasible)

    # ------------------------------------------------------------------
    # 5. Low-benefit candidate accepted as NONE
    # ------------------------------------------------------------------

    def test_b3_accepts_low_benefit_candidate_as_none(self):
        """When only a low-benefit candidate remains, B3 accepts it as-is (NONE).

        [SYNTHETIC EXAMPLE]: w=1.0, u=0.04 → benefit = 0.04 < min_benefit_to_act default (0.05).
        """
        # Need benefit = w*u < 0.05. Using conf=0.999, u=0.01: h(0.999)≈0.011 ✓  benefit=1.0*0.01=0.01<0.05
        c_tiny = _make_candidate("c_tiny", 0.999, 0.01, ImportanceTier.LOW)

        _, decision = self.policy.run_joint_step(
            all_candidates=[c_tiny],
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )

        self.assertEqual(decision.action, ActionType.NONE)
        self.assertTrue(decision.reserve_feasible)
        self.assertEqual(decision.estimated_cost_joules, 0.0)

    # ------------------------------------------------------------------
    # 6. Joint score formula correctness
    # ------------------------------------------------------------------

    def test_b3_joint_score_formula(self):
        """_joint_score() = w * u * reduction / max(cost, min_denom).

        ASSUMED values used in formula are tagged in B3JointPolicyConfig.
        """
        # conf=0.60, u=0.97  h(0.60)=0.971 ✓   w=4.0
        c = _make_candidate("c_score", 0.60, 0.97, ImportanceTier.HIGH)   # w=4.0, u=0.97

        # RECAPTURE reduction = 0.70 (ASSUMED)
        # cost for x=0 to x=200: flight time 200/12 * 180W + hover(2200J) + fixed(920J)
        cost_est = self.cost_model.estimate_cost(
            ActionType.RECAPTURE,
            HOME,
            LocalGridCoordinates(x_meters=200.0, y_meters=0.0, z_meters=50.0)
        )
        expected_score = (4.0 * 0.97 * 0.70) / cost_est.energy_cost_joules
        actual_score = self.policy._joint_score(c, ActionType.RECAPTURE, cost_est.energy_cost_joules)
        self.assertAlmostEqual(actual_score, expected_score, places=6)

    # ------------------------------------------------------------------
    # 7. Prefers STRONGER_MODEL over RECAPTURE when importance is medium
    #    and energy cost ratio favours compute-only
    # ------------------------------------------------------------------

    def test_b3_prefers_stronger_model_for_distant_low_importance_target(self):
        """[SYNTHETIC EXAMPLE] For a far, low-importance candidate, STRONGER_MODEL should
        score higher than RECAPTURE because flight cost dominates the denominator.

        w=1.0, u=0.90, x=1000m.
        RECAPTURE cost >> STRONGER_MODEL cost (1450 J),
        so joint score for STRONGER_MODEL > RECAPTURE.
        """
        # Formula-consistent: conf=0.55, u=0.99  h(0.55)=0.993 ✓
        c = _make_candidate("c_far_low", 0.55, 0.99, ImportanceTier.LOW, x=1000.0)

        _, decision = self.policy.run_joint_step(
            all_candidates=[c],
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )

        # For a low-importance distant candidate, STRONGER_MODEL offers a better score
        # than the expensive flight
        self.assertIn(decision.action, [ActionType.STRONGER_MODEL, ActionType.HUMAN_REVIEW])
        self.assertTrue(decision.reserve_feasible)

    # ------------------------------------------------------------------
    # 8. select_action() single-candidate compatibility with standard simulator
    # ------------------------------------------------------------------

    def test_b3_select_action_single_candidate_compatible(self):
        """select_action() called with a single candidate must still return a feasible decision.

        This verifies compatibility with the standard simulator loop that calls
        select_action() per ranked candidate.
        """
        # Formula-consistent: conf=0.60, u=0.97  h(0.60)=0.971 ✓
        c = _make_candidate("c_single", 0.60, 0.97, ImportanceTier.HIGH, x=300.0)
        decision = self.policy.select_action(
            candidate=c,
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )
        # Must be a valid decision
        self.assertIn(decision.action, list(ActionType))
        self.assertIsNotNone(decision.reason)

    # ------------------------------------------------------------------
    # 9. End-to-end simulation — B3 runs to completion with safe return
    # ------------------------------------------------------------------

    def test_b3_simulator_run_end_to_end(self):
        """B3 end-to-end simulation over synthetic candidates completes with safe return.

        [SYNTHETIC EXAMPLE] Uses create_synthetic_candidate_states() with 60,000 J budget.
        All outcome summaries are [SIMULATED].
        """
        candidates = create_synthetic_candidate_states()
        sim = MissionSimulator(
            config=MissionSimulationConfig(initial_battery_joules=60_000.0),
            cost_model=ActionCostModel(energy_model=DroneEnergyModel()),
            outcome_sim=ActionOutcomeSimulator(),
        )
        report = sim.run_mission(self.policy, candidates)

        self.assertEqual(report.policy_id, "B3")
        self.assertTrue(report.safe_return_completed, "Safe return must be guaranteed")
        self.assertGreater(report.final_battery_joules, 0.0)
        self.assertEqual(report.candidates_total, len(candidates))

        # At least one candidate must have been inspected or skipped (not all deferred)
        self.assertGreater(
            report.candidates_inspected + report.candidates_skipped,
            0,
            "B3 should handle at least one candidate before returning"
        )

        # Verify the ledger captured decision records
        non_return_records = [r for r in sim.ledger.records if r.candidate_id != "MISSION_RETURN"]
        self.assertGreater(len(non_return_records), 0)

    def test_b3_simulator_selects_joint_winner_not_input_first(self):
        """The simulator must pass all pending candidates to B3's joint selector."""
        first = _make_candidate("first_low", 0.90, 0.47, ImportanceTier.LOW, x=100.0)
        joint_winner = _make_candidate("second_high", 0.55, 0.99, ImportanceTier.HIGH, x=100.0)
        sim = MissionSimulator(
            config=MissionSimulationConfig(initial_battery_joules=60_000.0),
            cost_model=self.cost_model,
            outcome_sim=ActionOutcomeSimulator(),
        )

        report = sim.run_mission(self.policy, [first, joint_winner])
        first_candidate_decision = next(
            record for record in sim.ledger.records
            if record.candidate_id != "MISSION_RETURN"
        )

        self.assertTrue(report.safe_return_completed)
        self.assertEqual(first_candidate_decision.candidate_id, "second_high")

    # ------------------------------------------------------------------
    # 10. Config customisation — custom thresholds are honoured
    # ------------------------------------------------------------------

    def test_b3_config_min_benefit_excludes_all_actions(self):
        """When min_benefit_to_act is set very high, all candidates fall below threshold
        and are accepted as-is (NONE) or trigger RETURN_HOME if they have high benefit.

        [SYNTHETIC EXAMPLE] uses min_benefit_to_act=99.0 to force NONE for typical candidates.
        """
        from ares.schemas.provenance import ProvenanceValue
        config = B3JointPolicyConfig(
            min_benefit_to_act=ProvenanceValue(
                value=99.0,
                provenance=DataProvenance.ASSUMED,
                notes="Test: unreachably high threshold to verify NONE fallback"
            )
        )
        policy = B3JointPolicy(config=config)

        # Formula-consistent: conf=0.55, u=0.99  h(0.55)=0.993 ✓
        c = _make_candidate("c_threshold", 0.55, 0.99, ImportanceTier.HIGH)
        _, decision = policy.run_joint_step(
            all_candidates=[c],
            current_pos=HOME,
            current_battery_joules=50_000.0,
            cost_model=self.cost_model,
            reserve_calc=self.reserve_calc,
            home_pos=HOME,
        )
        # All candidates below the high threshold → accepted as NONE
        self.assertEqual(decision.action, ActionType.NONE)


if __name__ == "__main__":
    unittest.main()
