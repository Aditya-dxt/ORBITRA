"""Abstract base policy interface for ARES."""

from abc import ABC, abstractmethod
from typing import List, NamedTuple, Optional

from ares.actions.models import ActionCostModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.schemas.candidate_state import ActionType, AresCandidateState, CandidateStatus
from ares.schemas.satquery_record import LocalGridCoordinates


class ActionSelectionDecision(NamedTuple):
    """The complete decision chosen by a policy for a candidate target."""
    action: ActionType
    estimated_cost_joules: float
    estimated_benefit: float
    is_flight_action: bool
    post_action_pos: LocalGridCoordinates
    reserve_feasible: bool
    reason: str


class BasePolicy(ABC):
    """Abstract base class for all ARES candidate scheduling and action policies."""

    def __init__(self, policy_id: str, policy_name: str):
        self.policy_id = policy_id
        self.policy_name = policy_name

    @abstractmethod
    def rank_candidates(
        self,
        candidates: List[AresCandidateState],
        current_pos: Optional[LocalGridCoordinates] = None,
    ) -> List[AresCandidateState]:
        """Ranks pending candidates according to the policy's prioritization rules.
        
        Optional current_pos allows spatial policies (e.g. B4) to evaluate
        transit distance dynamically from the current UAV location.
        """
        pass

    @abstractmethod
    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Calculates expected mission benefit for inspecting this candidate."""
        pass

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
        """Selects the action for a candidate and checks post-action return reserve feasibility.
        
        Default baseline implementation evaluates physical RECAPTURE.
        Specialized policies (such as B2 Adaptive Computation) override this method.
        """
        target_pos = candidate.detection.region.local_grid
        if target_pos is None:
            target_pos = LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)

        cost_est = cost_model.estimate_cost(ActionType.RECAPTURE, current_pos, target_pos)
        benefit = self.evaluate_benefit(candidate)

        reserve_check = reserve_calc.check_action_feasibility(
            current_battery_joules=current_battery_joules,
            estimated_action_joules=cost_est.energy_cost_joules,
            post_action_pos=target_pos,
            home_pos=home_pos
        )

        if reserve_check.is_feasible:
            return ActionSelectionDecision(
                action=ActionType.RECAPTURE,
                estimated_cost_joules=cost_est.energy_cost_joules,
                estimated_benefit=benefit,
                is_flight_action=True,
                post_action_pos=target_pos,
                reserve_feasible=True,
                reason=f"Policy {self.policy_id} selected RECAPTURE. {reserve_check.reason}"
            )
        else:
            return ActionSelectionDecision(
                action=ActionType.RETURN_HOME,
                estimated_cost_joules=0.0,
                estimated_benefit=0.0,
                is_flight_action=False,
                post_action_pos=current_pos,
                reserve_feasible=False,
                reason=f"Return reserve guardrail triggered: {reserve_check.reason}"
            )

    def get_pending_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """Filters candidates whose lifecycle status is PENDING."""
        return [c for c in candidates if c.status == CandidateStatus.PENDING]
