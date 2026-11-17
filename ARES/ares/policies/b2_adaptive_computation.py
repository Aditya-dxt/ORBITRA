"""B2: Adaptive Computation Policy.

Dynamically selects the computation depth and verification modality
(NONE, STRONGER_MODEL, RECAPTURE, or HUMAN_REVIEW) per candidate
based on detector uncertainty, mission importance, action energy costs,
and remaining battery budget under the return-reserve constraint.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from ares.actions.models import ActionCostModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.base import ActionSelectionDecision, BasePolicy
from ares.schemas.candidate_state import ActionType, AresCandidateState
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


class B2AdaptiveComputationConfig(BaseModel):
    """Configurable thresholds for adaptive computation and action allocation."""
    
    # Uncertainty below which no extra compute or flight is needed
    low_uncertainty_threshold: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.30,
            provenance=DataProvenance.ASSUMED,
            notes="Uncertainty threshold below which baseline detection is accepted (no extra compute)"
        )
    )
    
    # Uncertainty above which high-capacity models or physical recapture are considered
    high_uncertainty_threshold: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.65,
            provenance=DataProvenance.ASSUMED,
            notes="Uncertainty threshold triggering high-tier verification"
        )
    )
    
    # Mission importance threshold for considering physical drone flight
    high_importance_threshold: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=4.0,
            provenance=DataProvenance.ASSUMED,
            notes="Minimum importance weight required to justify a physical flight sortie"
        )
    )
    
    # Battery fraction below which drone conserves flight energy and prefers onboard/offloaded compute
    min_battery_fraction_for_flight: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.35,
            provenance=DataProvenance.ASSUMED,
            notes="Battery fraction below which flight sorties are restricted to conserve return energy"
        )
    )
    
    allow_human_review_fallback: ProvenanceValue[bool] = Field(
        default_factory=lambda: ProvenanceValue(
            value=True,
            provenance=DataProvenance.ASSUMED,
            notes="Whether to permit fallback to human review queue when compute energy is tight"
        )
    )


class B2AdaptiveComputationPolicy(BasePolicy):
    """B2: Adaptive computation allocation policy."""

    def __init__(self, config: Optional[B2AdaptiveComputationConfig] = None):
        super().__init__(
            policy_id="B2",
            policy_name="Adaptive Computation"
        )
        self.config = config or B2AdaptiveComputationConfig()

    def rank_candidates(
        self,
        candidates: List[AresCandidateState],
        current_pos: Optional[LocalGridCoordinates] = None,
    ) -> List[AresCandidateState]:
        """Ranks pending candidates prioritizing highest expected information gain (importance * uncertainty)."""
        pending = self.get_pending_candidates(candidates)
        return sorted(
            pending,
            key=lambda c: (
                float(c.importance_weight.value) * c.detection.uncertainty,
                c.detection.uncertainty
            ),
            reverse=True
        )

    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Calculates expected mission benefit: importance_weight * uncertainty."""
        weight = float(candidate.importance_weight.value)
        unc = candidate.detection.uncertainty
        return round(weight * unc, 4)

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
        """Dynamically selects an action matching the candidate's ambiguity and available budget."""
        u = candidate.detection.uncertainty
        w = float(candidate.importance_weight.value)
        target_pos = candidate.detection.region.local_grid
        if target_pos is None:
            target_pos = LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)

        low_u = self.config.low_uncertainty_threshold.value
        high_u = self.config.high_uncertainty_threshold.value
        high_w = self.config.high_importance_threshold.value
        min_batt_frac = self.config.min_battery_fraction_for_flight.value

        benefit = self.evaluate_benefit(candidate)
        battery_fraction = (current_battery_joules / initial_battery_joules) if initial_battery_joules > 0 else 0.0

        # Branch 1: Low uncertainty - accept baseline without additional compute
        if u < low_u:
            return ActionSelectionDecision(
                action=ActionType.NONE,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=True,
                reason=(
                    f"Candidate uncertainty ({u:.2f} < {low_u:.2f}) is already low; "
                    f"baseline detection accepted without additional compute."
                )
            )

        # Branch 2: High uncertainty & High importance -> Candidate for physical RECAPTURE
        if u >= high_u and w >= high_w and battery_fraction >= min_batt_frac:
            recapture_cost = cost_model.estimate_cost(ActionType.RECAPTURE, current_pos, target_pos)
            reserve_check = reserve_calc.check_action_feasibility(
                current_battery_joules=current_battery_joules,
                estimated_action_joules=recapture_cost.energy_cost_joules,
                post_action_pos=target_pos,
                home_pos=home_pos
            )
            if reserve_check.is_feasible:
                return ActionSelectionDecision(
                    action=ActionType.RECAPTURE,
                    estimated_cost_joules=recapture_cost.energy_cost_joules,
                    estimated_benefit=benefit,
                    is_flight_action=True,
                    post_action_pos=target_pos,
                    reserve_feasible=True,
                    reason=(
                        f"High uncertainty ({u:.2f}) and high importance ({w:.1f}) warrant "
                        f"physical RECAPTURE sortie; return reserve satisfied."
                    )
                )
            # If RECAPTURE fails reserve check, we adaptively fall through to STRONGER_MODEL below!

        # Branch 3: Moderate uncertainty / moderate importance OR downscaled from flight -> STRONGER_MODEL
        stronger_cost = cost_model.estimate_cost(ActionType.STRONGER_MODEL, current_pos, current_pos)
        reserve_check_stronger = reserve_calc.check_action_feasibility(
            current_battery_joules=current_battery_joules,
            estimated_action_joules=stronger_cost.energy_cost_joules,
            post_action_pos=current_pos,
            home_pos=home_pos
        )

        if reserve_check_stronger.is_feasible:
            reason = (
                f"Physical recapture infeasible under reserve or restricted by budget ({battery_fraction:.1%}); "
                f"adaptively downscaled to STRONGER_MODEL inference."
                if (u >= high_u and w >= high_w)
                else f"Moderate uncertainty ({u:.2f}) warrants STRONGER_MODEL inference (zero flight energy consumed)."
            )
            return ActionSelectionDecision(
                action=ActionType.STRONGER_MODEL,
                estimated_cost_joules=stronger_cost.energy_cost_joules,
                estimated_benefit=round(benefit * 0.8, 4),
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=True,
                reason=reason
            )

        # Branch 4: Low remaining energy -> Fallback to HUMAN_REVIEW triage if permitted
        if self.config.allow_human_review_fallback.value:
            human_cost = cost_model.estimate_cost(ActionType.HUMAN_REVIEW, current_pos, current_pos)
            reserve_check_human = reserve_calc.check_action_feasibility(
                current_battery_joules=current_battery_joules,
                estimated_action_joules=human_cost.energy_cost_joules,
                post_action_pos=current_pos,
                home_pos=home_pos
            )
            if reserve_check_human.is_feasible:
                return ActionSelectionDecision(
                    action=ActionType.HUMAN_REVIEW,
                    estimated_cost_joules=human_cost.energy_cost_joules,
                    estimated_benefit=round(benefit * 0.9, 4),
                    is_flight_action=False,
                    post_action_pos=current_pos,
                    reserve_feasible=True,
                    reason="Energy budget too low for automated models; routed to HUMAN_REVIEW queue."
                )

        # Branch 5: Infeasible under all modalities
        return ActionSelectionDecision(
            action=ActionType.RETURN_HOME,
            estimated_cost_joules=0.0,
            estimated_benefit=0.0,
            is_flight_action=False,
            post_action_pos=current_pos,
            reserve_feasible=False,
            reason="Return reserve constraint prevents all available verification actions."
        )
