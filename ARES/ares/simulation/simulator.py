"""Mission simulator executing ARES decision policies under energy constraints.

Enforces the return-reserve guardrail and logs all events to the decision ledger.
All results and action outcomes are explicitly marked SIMULATED.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from ares.actions.models import ActionCostModel, ActionOutcomeSimulator
from ares.energy.model import DroneEnergyModel, euclidean_distance
from ares.energy.reserve import ReturnReserveCalculator
from ares.energy.units import joules_to_wh
from ares.ledger.decision_ledger import DecisionLedger
from ares.policies.base import BasePolicy
from ares.schemas.candidate_state import (
    ActionType,
    AresCandidateState,
    CandidateStatus,
    EvidenceRecord,
)
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import LocalGridCoordinates


class MissionSimulationConfig(BaseModel):
    """Configuration for a simulated verification mission sortie."""
    initial_battery_joules: float = Field(
        default=60_000.0,
        gt=0.0,
        description="Initial mission energy budget in Joules (~16.67 Wh)"
    )
    home_position: LocalGridCoordinates = Field(
        default_factory=lambda: LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
    )
    hover_duration_sec: float = Field(
        default=10.0,
        ge=0.0,
        description="Target dwell time for simulated sensor capture"
    )


class MissionSimulationReport(BaseModel):
    """Execution summary of a completed mission simulation run."""
    policy_id: str
    policy_name: str
    provenance: DataProvenance = DataProvenance.SIMULATED
    initial_battery_joules: float
    initial_battery_wh: float
    final_battery_joules: float
    final_battery_wh: float
    total_energy_spent_actions_joules: float
    total_energy_spent_actions_wh: float
    return_flight_energy_joules: float
    return_flight_energy_wh: float
    safe_return_completed: bool
    candidates_total: int
    candidates_inspected: int
    candidates_deferred: int
    candidates_skipped: int
    ledger_records_count: int
    summary_message: str


class MissionSimulator:
    """Discrete-event simulation engine for testing ARES policies."""

    def __init__(
        self,
        config: Optional[MissionSimulationConfig] = None,
        energy_model: Optional[DroneEnergyModel] = None,
        reserve_calc: Optional[ReturnReserveCalculator] = None,
        cost_model: Optional[ActionCostModel] = None,
        outcome_sim: Optional[ActionOutcomeSimulator] = None
    ):
        self.config = config or MissionSimulationConfig()
        self.energy_model = energy_model or DroneEnergyModel()
        self.reserve_calc = reserve_calc or ReturnReserveCalculator(energy_model=self.energy_model)
        self.cost_model = cost_model or ActionCostModel(energy_model=self.energy_model)
        self.outcome_sim = outcome_sim or ActionOutcomeSimulator()
        self.ledger = DecisionLedger()

    def run_mission(
        self,
        policy: BasePolicy,
        candidates: List[AresCandidateState]
    ) -> MissionSimulationReport:
        """Executes a full simulated sortie over candidates using the selected policy."""
        current_battery = self.config.initial_battery_joules
        current_pos = self.config.home_position
        home = self.config.home_position

        active_candidates = [c.model_copy(deep=True) for c in candidates]

        while True:
            ranked_queue = policy.rank_candidates(active_candidates, current_pos=current_pos)
            if not ranked_queue:
                break

            # Joint policies choose the candidate and action from the full
            # pending set. Sequential baselines keep the rank-then-act path.
            joint_selector = getattr(policy, "run_joint_step", None)
            if callable(joint_selector):
                target, decision = joint_selector(
                    all_candidates=active_candidates,
                    current_pos=current_pos,
                    current_battery_joules=current_battery,
                    cost_model=self.cost_model,
                    reserve_calc=self.reserve_calc,
                    home_pos=home,
                    initial_battery_joules=self.config.initial_battery_joules,
                )
                # If every candidate-action pair is infeasible, anchor the
                # abort ledger entry to a pending candidate.
                if target is None:
                    target = ranked_queue[0]
            else:
                target = ranked_queue[0]
                decision = policy.select_action(
                    candidate=target,
                    current_pos=current_pos,
                    current_battery_joules=current_battery,
                    cost_model=self.cost_model,
                    reserve_calc=self.reserve_calc,
                    home_pos=home,
                    initial_battery_joules=self.config.initial_battery_joules
                )

            if decision.reserve_feasible:
                battery_before = current_battery
                current_battery -= decision.estimated_cost_joules
                
                # Flight actions relocate drone; non-flight actions (STRONGER_MODEL, HUMAN_REVIEW) do not
                if decision.is_flight_action:
                    current_pos = decision.post_action_pos

                required_reserve = self.reserve_calc.calculate_required_reserve_joules(
                    decision.post_action_pos, home
                )

                if decision.action == ActionType.NONE:
                    target.status = CandidateStatus.SKIPPED
                    target.assigned_action = ActionType.NONE
                    target.estimated_benefit = 0.0
                    target.estimated_energy_joules = 0.0
                    target.reserve_feasible = True
                    target.decision_reason = decision.reason

                    self.ledger.record_decision(
                        candidate_id=target.detection.candidate_id,
                        policy_id=policy.policy_id,
                        selected_action=ActionType.NONE,
                        action_energy_joules=0.0,
                        battery_before_joules=battery_before,
                        battery_after_joules=current_battery,
                        required_reserve_joules=required_reserve,
                        reserve_feasible=True,
                        estimated_benefit=0.0,
                        reason=decision.reason,
                        simulated_outcome="[SIMULATED] Candidate accepted without additional compute",
                        extra_metadata={"action": "NONE"}
                    )
                else:
                    target.status = CandidateStatus.INSPECTED
                    target.assigned_action = decision.action
                    target.estimated_benefit = decision.estimated_benefit
                    target.estimated_energy_joules = decision.estimated_cost_joules
                    target.reserve_feasible = True
                    target.decision_reason = decision.reason

                    # Generate simulated outcome
                    sim_outcome = self.outcome_sim.simulate_outcome(decision.action, target)

                    target.evidence_history.append(
                        EvidenceRecord(
                            action=decision.action,
                            timestamp=target.detection.timestamp,
                            energy_spent_joules=decision.estimated_cost_joules,
                            simulated_outcome=sim_outcome.outcome_summary,
                            notes=f"Post-action location: x={decision.post_action_pos.x_meters}m, y={decision.post_action_pos.y_meters}m"
                        )
                    )

                    self.ledger.record_decision(
                        candidate_id=target.detection.candidate_id,
                        policy_id=policy.policy_id,
                        selected_action=decision.action,
                        action_energy_joules=decision.estimated_cost_joules,
                        battery_before_joules=battery_before,
                        battery_after_joules=current_battery,
                        required_reserve_joules=required_reserve,
                        reserve_feasible=True,
                        estimated_benefit=decision.estimated_benefit,
                        reason=decision.reason,
                        simulated_outcome=sim_outcome.outcome_summary,
                        extra_metadata={"post_action_pos": decision.post_action_pos.model_dump()}
                    )
            else:
                # Infeasible under return reserve constraint -> abort sortie to protect reserve
                target.status = CandidateStatus.DEFERRED
                target.assigned_action = ActionType.RETURN_HOME
                target.estimated_benefit = decision.estimated_benefit
                target.estimated_energy_joules = decision.estimated_cost_joules
                target.reserve_feasible = False
                target.decision_reason = decision.reason

                required_reserve = self.reserve_calc.calculate_required_reserve_joules(
                    decision.post_action_pos, home
                )

                self.ledger.record_decision(
                    candidate_id=target.detection.candidate_id,
                    policy_id=policy.policy_id,
                    selected_action=ActionType.RETURN_HOME,
                    action_energy_joules=0.0,
                    battery_before_joules=current_battery,
                    battery_after_joules=current_battery,
                    required_reserve_joules=required_reserve,
                    reserve_feasible=False,
                    estimated_benefit=0.0,
                    reason=decision.reason,
                    simulated_outcome="[SIMULATED] Sortie terminated to guarantee safe return reserve",
                    extra_metadata={"deferred_candidate": target.detection.candidate_id}
                )

                for c in active_candidates:
                    if c.status == CandidateStatus.PENDING:
                        c.status = CandidateStatus.DEFERRED
                        c.decision_reason = "Mission aborted early to preserve return reserve"
                break

        # Final return flight from current_pos back to home base
        return_energy = self.energy_model.transit_energy_joules(current_pos, home)
        safe_return = (current_battery >= return_energy)
        battery_final = max(0.0, current_battery - return_energy)

        self.ledger.record_decision(
            candidate_id="MISSION_RETURN",
            policy_id=policy.policy_id,
            selected_action=ActionType.RETURN_HOME,
            action_energy_joules=return_energy,
            battery_before_joules=current_battery,
            battery_after_joules=battery_final,
            required_reserve_joules=0.0,
            reserve_feasible=safe_return,
            estimated_benefit=0.0,
            reason="UAV transit from mission position back to home base",
            simulated_outcome="[SIMULATED] Safe return flight completed to home base",
            extra_metadata={"return_distance_m": euclidean_distance(current_pos, home)}
        )

        inspected_count = sum(1 for c in active_candidates if c.status == CandidateStatus.INSPECTED)
        deferred_count = sum(1 for c in active_candidates if c.status == CandidateStatus.DEFERRED)
        skipped_count = sum(1 for c in active_candidates if c.status == CandidateStatus.SKIPPED)

        total_action_energy = self.ledger.total_energy_spent_joules()

        report = MissionSimulationReport(
            policy_id=policy.policy_id,
            policy_name=policy.policy_name,
            provenance=DataProvenance.SIMULATED,
            initial_battery_joules=self.config.initial_battery_joules,
            initial_battery_wh=round(joules_to_wh(self.config.initial_battery_joules), 2),
            final_battery_joules=round(battery_final, 1),
            final_battery_wh=round(joules_to_wh(battery_final), 2),
            total_energy_spent_actions_joules=round(total_action_energy, 1),
            total_energy_spent_actions_wh=round(joules_to_wh(total_action_energy), 2),
            return_flight_energy_joules=round(return_energy, 1),
            return_flight_energy_wh=round(joules_to_wh(return_energy), 2),
            safe_return_completed=safe_return,
            candidates_total=len(active_candidates),
            candidates_inspected=inspected_count,
            candidates_deferred=deferred_count,
            candidates_skipped=skipped_count,
            ledger_records_count=len(self.ledger.records),
            summary_message=(
                f"[SIMULATED] Sortie under {policy.policy_id} ({policy.policy_name}) completed: "
                f"{inspected_count} inspected, {skipped_count} skipped, {deferred_count} deferred. "
                f"Safe return: {safe_return}."
            )
        )
        return report
