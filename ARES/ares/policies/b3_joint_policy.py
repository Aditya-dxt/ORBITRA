"""B3: Joint Policy.

Jointly selects both WHICH candidate to handle and WHICH action to apply in a
single decision step, rather than separating candidate ranking from action
selection as B0/B1/B2 do.

Decision loop per step:
  1. Enumerate all PENDING candidates.
  2. For each candidate, enumerate all supported actions (RECAPTURE, STRONGER_MODEL,
     HUMAN_REVIEW, NONE-accept) and compute energy cost and expected benefit.
  3. Apply the return-reserve guardrail to every (candidate, action) pair.
  4. Score each feasible pair with the joint objective:
         score = importance_weight * expected_uncertainty_reduction / action_energy_cost_joules
     Pairs with zero cost (NONE / HUMAN_REVIEW-at-50J) are handled by special
     cases to avoid division-by-zero (see below).
  5. Select the globally highest-scoring feasible pair and execute that action
     on that candidate. Mark all other candidates PENDING until the next step.
  6. Repeat until no candidate-action pair is feasible (return reserve forces abort).

Design trade-offs:
- Complexity per step is O(C × A) where C = remaining PENDING candidates,
  A = number of action types (3 substantive + 1 accept). Acceptable for a
  research prototype with tens of candidates.
- The objective function (benefit / cost) shares structure with B4 (Greedy
  Benefit-per-Energy) but B3 evaluates the joint space in one step, while B4
  is defined to greedily maximise marginal utility per Joule across the
  combined (candidate × action) space. B3 and B4 therefore differ in scope
  and implementation.

All thresholds, benefit scalars, and uncertainty reduction rates are tagged
ASSUMED.  All simulated outcomes are tagged SIMULATED.
"""

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from ares.actions.models import ActionCostModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.base import ActionSelectionDecision, BasePolicy
from ares.schemas.candidate_state import ActionType, AresCandidateState, CandidateStatus
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class B3JointPolicyConfig(BaseModel):
    """Configurable parameters for the B3 joint candidate-action objective.

    All values are tagged ASSUMED — they are starting engineering estimates,
    not calibrated from real drone flights or annotated datasets.
    """

    # Uncertainty reduction fractions per action (fractional, 0-1 range)
    # e.g. 0.70 means the action reduces prior uncertainty by 70 %.
    recapture_uncertainty_reduction: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.70,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Fraction by which RECAPTURE reduces candidate uncertainty. "
                "ASSUMED starting estimate; not measured from physical flights."
            )
        )
    )
    stronger_model_uncertainty_reduction: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.40,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Fraction by which STRONGER_MODEL reduces candidate uncertainty. "
                "ASSUMED starting estimate; not measured."
            )
        )
    )
    human_review_uncertainty_reduction: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.95,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Fraction by which HUMAN_REVIEW reduces candidate uncertainty "
                "(conclusive analyst resolution). ASSUMED starting estimate."
            )
        )
    )

    # Minimum expected benefit score to consider ANY action on a candidate.
    # Candidates below this threshold are accepted as-is (NONE) without compute.
    min_benefit_to_act: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.05,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Minimum expected joint benefit before any verification action "
                "is considered. Candidates scoring below are accepted as-is."
            )
        )
    )

    # Minimum energy denominator guard (joules) to prevent division-by-zero
    # for near-zero cost actions such as HUMAN_REVIEW (50 J).
    min_cost_denominator_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=50.0,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Floor value for energy cost in the benefit/cost ratio, "
                "preventing division-by-zero for very cheap actions."
            )
        )
    )

    # Allow human review as a candidate action (False disables the branch)
    allow_human_review: ProvenanceValue[bool] = Field(
        default_factory=lambda: ProvenanceValue(
            value=True,
            provenance=DataProvenance.ASSUMED,
            notes="Whether HUMAN_REVIEW is included in the joint action space."
        )
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

class B3JointPolicy(BasePolicy):
    """B3: Joint candidate-and-action selection policy.

    At every decision step, evaluates all feasible (candidate, action) pairs
    and executes the globally highest-scoring pair under the return-reserve
    constraint.
    """

    def __init__(self, config: Optional[B3JointPolicyConfig] = None):
        super().__init__(policy_id="B3", policy_name="Joint Policy")
        self.config = config or B3JointPolicyConfig()

    # ------------------------------------------------------------------
    # BasePolicy abstract methods
    # ------------------------------------------------------------------

    def rank_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """B3 does not pre-sort candidates independently.

        Returns pending candidates in input order; ordering decisions are made
        inside select_action() during joint evaluation.
        """
        return self.get_pending_candidates(candidates)

    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Baseline benefit proxy: importance_weight * uncertainty.

        Used when select_action() is called without an explicit action context.
        The joint objective uses action-specific expected reduction instead.
        """
        w = float(candidate.importance_weight.value)
        u = candidate.detection.uncertainty
        return round(w * u, 4)

    # ------------------------------------------------------------------
    # Joint objective helpers
    # ------------------------------------------------------------------

    def _expected_uncertainty_reduction(self, action: ActionType) -> float:
        """Returns the ASSUMED expected fractional uncertainty reduction for an action."""
        if action == ActionType.RECAPTURE:
            return self.config.recapture_uncertainty_reduction.value
        elif action == ActionType.STRONGER_MODEL:
            return self.config.stronger_model_uncertainty_reduction.value
        elif action == ActionType.HUMAN_REVIEW:
            return self.config.human_review_uncertainty_reduction.value
        return 0.0  # NONE / RETURN_HOME

    def _joint_score(
        self,
        candidate: AresCandidateState,
        action: ActionType,
        action_cost_joules: float,
    ) -> float:
        """Computes the joint benefit/cost objective score for one (candidate, action) pair.

        score = importance_weight * prior_uncertainty * uncertainty_reduction_rate
                ------------------------------------------------------------------
                              max(action_cost_joules, min_denominator)

        All inputs are ASSUMED / SIMULATED.
        """
        w = float(candidate.importance_weight.value)
        u = candidate.detection.uncertainty
        reduction = self._expected_uncertainty_reduction(action)
        numerator = w * u * reduction
        denominator = max(action_cost_joules, self.config.min_cost_denominator_joules.value)
        return numerator / denominator

    # ------------------------------------------------------------------
    # Core joint selection
    # ------------------------------------------------------------------

    def select_action(
        self,
        candidate: AresCandidateState,
        current_pos: LocalGridCoordinates,
        current_battery_joules: float,
        cost_model: ActionCostModel,
        reserve_calc: ReturnReserveCalculator,
        home_pos: LocalGridCoordinates,
        initial_battery_joules: float = 60_000.0,
        # Optional: remaining PENDING candidates for joint evaluation
        # (populated by simulator via the extended interface below)
        all_candidates: Optional[List[AresCandidateState]] = None,
    ) -> ActionSelectionDecision:
        """Evaluates all feasible (candidate, action) pairs and selects the best joint score.

        When `all_candidates` is provided (by the B3-aware simulator path), the
        joint evaluation ranges over all pending candidates.  When called from
        the standard simulator path (which passes only one candidate at a time),
        evaluation is restricted to that single candidate — this preserves
        compatibility with the existing simulator loop while still choosing the
        best action for the given candidate using the joint objective.
        """
        pool: List[AresCandidateState] = (
            [c for c in all_candidates if c.status == CandidateStatus.PENDING]
            if all_candidates is not None
            else [candidate]
        )

        min_benefit = self.config.min_benefit_to_act.value
        actions_to_consider = [
            ActionType.RECAPTURE,
            ActionType.STRONGER_MODEL,
        ]
        if self.config.allow_human_review.value:
            actions_to_consider.append(ActionType.HUMAN_REVIEW)

        best_score: float = -1.0
        best_decision: Optional[ActionSelectionDecision] = None
        best_candidate: Optional[AresCandidateState] = None

        for cand in pool:
            baseline_benefit = self.evaluate_benefit(cand)
            if baseline_benefit < min_benefit:
                # Candidate has negligible benefit under any action — accept as-is later
                continue

            target_pos = cand.detection.region.local_grid
            if target_pos is None:
                target_pos = LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)

            for action in actions_to_consider:
                # Determine post-action drone position for reserve check
                if action == ActionType.RECAPTURE:
                    post_action_pos = target_pos
                    is_flight = True
                else:
                    post_action_pos = current_pos
                    is_flight = False

                cost_est = cost_model.estimate_cost(action, current_pos, target_pos)
                reserve_check = reserve_calc.check_action_feasibility(
                    current_battery_joules=current_battery_joules,
                    estimated_action_joules=cost_est.energy_cost_joules,
                    post_action_pos=post_action_pos,
                    home_pos=home_pos,
                )

                if not reserve_check.is_feasible:
                    continue  # Skip infeasible pairs — reserve guardrail enforced unconditionally

                score = self._joint_score(cand, action, cost_est.energy_cost_joules)
                if score > best_score:
                    best_score = score
                    best_candidate = cand
                    best_decision = ActionSelectionDecision(
                        action=action,
                        estimated_cost_joules=cost_est.energy_cost_joules,
                        estimated_benefit=round(
                            float(cand.importance_weight.value)
                            * cand.detection.uncertainty
                            * self._expected_uncertainty_reduction(action),
                            4
                        ),
                        is_flight_action=is_flight,
                        post_action_pos=post_action_pos,
                        reserve_feasible=True,
                        reason=(
                            f"[B3-JOINT] Best joint score {score:.4f} for candidate "
                            f"'{cand.detection.candidate_id}' + {action.value}. "
                            f"w={float(cand.importance_weight.value):.1f}, "
                            f"u={cand.detection.uncertainty:.2f}, "
                            f"reduction={self._expected_uncertainty_reduction(action):.0%}, "
                            f"cost={cost_est.energy_cost_joules:.0f}J"
                        )
                    )

        # Case: no feasible pair found above minimum benefit threshold
        if best_decision is None:
            # Check whether any candidate can be accepted as-is (NONE)
            for cand in pool:
                baseline_benefit = self.evaluate_benefit(cand)
                if baseline_benefit < min_benefit:
                    # Accept this candidate as-is (negligible benefit)
                    return ActionSelectionDecision(
                        action=ActionType.NONE,
                        estimated_cost_joules=0.0,
                        estimated_benefit=0.0,
                        is_flight_action=False,
                        post_action_pos=current_pos,
                        reserve_feasible=True,
                        reason=(
                            f"[B3-JOINT] Candidate '{cand.detection.candidate_id}' has "
                            f"benefit {baseline_benefit:.4f} < threshold {min_benefit:.4f}; "
                            f"accepted as-is without additional verification."
                        )
                    )
            # All remaining pairs are infeasible under reserve — force return
            return ActionSelectionDecision(
                action=ActionType.RETURN_HOME,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=False,
                reason=(
                    "[B3-JOINT] Return-reserve constraint prevents all remaining "
                    "candidate-action pairs. Initiating safe return to home base."
                )
            )

        # Attach selected candidate identity to the decision reason
        # (simulator uses candidate passed in; for joint runs the best_candidate
        # may differ — simulator handles candidate update via best_candidate ref)
        self._last_selected_candidate = best_candidate
        return best_decision

    # ------------------------------------------------------------------
    # Joint mission runner (used by B3-aware simulator path)
    # ------------------------------------------------------------------

    def run_joint_step(
        self,
        all_candidates: List[AresCandidateState],
        current_pos: LocalGridCoordinates,
        current_battery_joules: float,
        cost_model: ActionCostModel,
        reserve_calc: ReturnReserveCalculator,
        home_pos: LocalGridCoordinates,
        initial_battery_joules: float = 60_000.0,
    ) -> Tuple[Optional[AresCandidateState], ActionSelectionDecision]:
        """Evaluates all pending (candidate, action) pairs and returns the best pair.

        Returns (selected_candidate, decision).  If no feasible pair exists,
        returns (None, RETURN_HOME decision).
        """
        self._last_selected_candidate = None
        # Use a dummy candidate from the pool as the select_action anchor
        pool = [c for c in all_candidates if c.status == CandidateStatus.PENDING]
        if not pool:
            dummy = all_candidates[0] if all_candidates else None
            return None, ActionSelectionDecision(
                action=ActionType.RETURN_HOME,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=False,
                reason="[B3-JOINT] No pending candidates remain."
            )

        decision = self.select_action(
            candidate=pool[0],  # anchor; actual selection is joint across all_candidates
            current_pos=current_pos,
            current_battery_joules=current_battery_joules,
            cost_model=cost_model,
            reserve_calc=reserve_calc,
            home_pos=home_pos,
            initial_battery_joules=initial_battery_joules,
            all_candidates=all_candidates,
        )
        return self._last_selected_candidate, decision
