"""B4: Greedy Benefit-per-Energy Baseline Policy.

Selects candidates maximizing marginal benefit per expended Joule (dB/dE)
using physical RECAPTURE (single-modality spatial dispatch baseline).

Distinct from B3 (Joint Policy):
- B4 is a single-action baseline (modality fixed to RECAPTURE, no action choice).
- B4 dynamically ranks pending candidates by marginal expected benefit per Joule
  of physical transit + inspection energy from the current UAV location:
      ratio = (w_c * u_c * r_recapture) / max(E_recapture(x_curr, x_c), E_min)
- B4 selects RECAPTURE if the post-action return-reserve guardrail is satisfied;
  otherwise, it triggers RETURN_HOME.
- In contrast, B3 co-optimizes the candidate and multi-modal action (RECAPTURE,
  STRONGER_MODEL, HUMAN_REVIEW) simultaneously.

All thresholds, benefit scalars, and reduction rates are tagged ASSUMED.
All simulated outcomes are tagged SIMULATED.
"""

from typing import List, Optional
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

class B4GreedyBenefitPerEnergyConfig(BaseModel):
    """Configurable parameters for Policy B4 (Greedy Benefit-per-Energy).

    All values are tagged ASSUMED — starting engineering estimates,
    not calibrated from physical flight trials.
    """

    # Expected fractional uncertainty reduction for physical RECAPTURE (0 to 1)
    recapture_uncertainty_reduction: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.70,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Expected fraction by which RECAPTURE cuts candidate uncertainty. "
                "ASSUMED starting estimate; not calibrated from flight logs."
            )
        )
    )

    # Minimum expected benefit threshold to dispatch UAV for verification
    min_benefit_to_act: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.05,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Minimum expected benefit score to justify UAV sortie. "
                "Candidates scoring below are accepted as-is (NONE)."
            )
        )
    )

    # Minimum energy denominator floor (Joules) to prevent numerical instability
    min_cost_denominator_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=50.0,
            provenance=DataProvenance.ASSUMED,
            notes=(
                "Floor value for energy cost in the benefit/energy ratio, "
                "preventing division-by-zero or extreme spikes."
            )
        )
    )

    # Verification modality: fixed to RECAPTURE for single-action dispatch baseline
    verification_action: ProvenanceValue[ActionType] = Field(
        default_factory=lambda: ProvenanceValue(
            value=ActionType.RECAPTURE,
            provenance=DataProvenance.ASSUMED,
            notes="Single verification action representing classical physical dispatch."
        )
    )


# ---------------------------------------------------------------------------
# Policy Implementation
# ---------------------------------------------------------------------------

class B4GreedyBenefitPerEnergyPolicy(BasePolicy):
    """B4: Greedy Benefit-per-Energy Baseline Policy.

    Ranks candidates greedily by expected mission benefit per expended Joule
    from the current drone location, and evaluates physical RECAPTURE under
    the post-action return-reserve guardrail.
    """

    def __init__(
        self,
        config: Optional[B4GreedyBenefitPerEnergyConfig] = None,
        cost_model: Optional[ActionCostModel] = None,
    ):
        super().__init__(
            policy_id="B4",
            policy_name="Greedy Benefit per Energy"
        )
        self.config = config or B4GreedyBenefitPerEnergyConfig()
        self.cost_model = cost_model or ActionCostModel()
        self.current_pos = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Calculates expected marginal mission benefit for physical verification.

        Formula:
            Delta B = importance_weight * uncertainty * recapture_reduction_rate
        """
        w = float(candidate.importance_weight.value)
        u = candidate.detection.uncertainty
        r = self.config.recapture_uncertainty_reduction.value
        return round(w * u * r, 4)

    def compute_marginal_ratio(
        self,
        candidate: AresCandidateState,
        from_pos: LocalGridCoordinates,
    ) -> float:
        """Computes marginal benefit per Joule (dB/dE) from a given position.

        ratio = Delta B(c) / max(E_recapture(from_pos -> target_pos), E_min)
        """
        benefit = self.evaluate_benefit(candidate)
        target_pos = candidate.detection.region.local_grid
        if target_pos is None:
            target_pos = LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)

        cost_est = self.cost_model.estimate_cost(ActionType.RECAPTURE, from_pos, target_pos)
        denom = max(cost_est.energy_cost_joules, self.config.min_cost_denominator_joules.value)
        return benefit / denom

    def rank_candidates(
        self,
        candidates: List[AresCandidateState],
        current_pos: Optional[LocalGridCoordinates] = None,
    ) -> List[AresCandidateState]:
        """Ranks pending candidates descending by marginal benefit per Joule (dB/dE).

        Dynamically evaluates transit energy from current_pos (or self.current_pos).
        Ties are broken by detector uncertainty, then candidate identifier.
        """
        pending = self.get_pending_candidates(candidates)
        if not pending:
            return []

        pos = current_pos if current_pos is not None else self.current_pos
        self.current_pos = pos

        return sorted(
            pending,
            key=lambda c: (
                self.compute_marginal_ratio(c, pos),
                c.detection.uncertainty,
                c.detection.candidate_id,
            ),
            reverse=True
        )

    def select_action(
        self,
        candidate: AresCandidateState,
        current_pos: LocalGridCoordinates,
        current_battery_joules: float,
        cost_model: ActionCostModel,
        reserve_calc: ReturnReserveCalculator,
        home_pos: LocalGridCoordinates,
        initial_battery_joules: float = 60_000.0,
    ) -> ActionSelectionDecision:
        """Selects RECAPTURE under the post-action return-reserve guardrail.

        If expected benefit is below min_benefit_to_act, accepts candidate as-is (NONE).
        If RECAPTURE violates the return-reserve constraint, triggers RETURN_HOME.
        """
        self.current_pos = current_pos
        min_benefit = self.config.min_benefit_to_act.value
        benefit = self.evaluate_benefit(candidate)

        if benefit < min_benefit:
            return ActionSelectionDecision(
                action=ActionType.NONE,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=True,
                reason=(
                    f"[B4-GREEDY] Candidate '{candidate.detection.candidate_id}' expected "
                    f"benefit {benefit:.4f} < threshold {min_benefit:.4f}; accepted as-is."
                )
            )

        target_pos = candidate.detection.region.local_grid
        if target_pos is None:
            target_pos = LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)

        cost_est = cost_model.estimate_cost(ActionType.RECAPTURE, current_pos, target_pos)
        reserve_check = reserve_calc.check_action_feasibility(
            current_battery_joules=current_battery_joules,
            estimated_action_joules=cost_est.energy_cost_joules,
            post_action_pos=target_pos,
            home_pos=home_pos,
        )

        denom = max(cost_est.energy_cost_joules, self.config.min_cost_denominator_joules.value)
        ratio = benefit / denom

        if reserve_check.is_feasible:
            return ActionSelectionDecision(
                action=ActionType.RECAPTURE,
                estimated_cost_joules=cost_est.energy_cost_joules,
                estimated_benefit=benefit,
                is_flight_action=True,
                post_action_pos=target_pos,
                reserve_feasible=True,
                reason=(
                    f"[B4-GREEDY] Selected RECAPTURE for '{candidate.detection.candidate_id}'. "
                    f"Benefit={benefit:.4f}, Energy={cost_est.energy_cost_joules:.1f}J, "
                    f"Ratio={ratio:.6f}. {reserve_check.reason}"
                )
            )
        else:
            return ActionSelectionDecision(
                action=ActionType.RETURN_HOME,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=False,
                reason=(
                    f"[B4-GREEDY] Return reserve guardrail triggered for RECAPTURE of "
                    f"'{candidate.detection.candidate_id}': {reserve_check.reason}. "
                    f"Initiating safe return to home base."
                )
            )
