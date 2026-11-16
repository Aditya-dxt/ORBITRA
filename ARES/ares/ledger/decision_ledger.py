"""Structured decision ledger and audit trail for ARES.

Records every policy evaluation, action selection, energy expenditure,
reserve feasibility check, and simulated outcome.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ares.energy.units import joules_to_wh
from ares.schemas.candidate_state import ActionType
from ares.schemas.provenance import DataProvenance


class DecisionRecord(BaseModel):
    """An immutable audit entry for an evaluated candidate decision."""
    decision_id: str = Field(..., description="Unique decision event identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp of decision"
    )
    candidate_id: str = Field(..., description="ID of the candidate evaluated")
    policy_id: str = Field(..., description="Active policy name (e.g. B0, B1)")
    selected_action: ActionType = Field(..., description="Action chosen by policy")
    action_energy_joules: float = Field(..., ge=0.0, description="Projected energy cost in Joules")
    action_energy_wh: float = Field(..., ge=0.0, description="Display energy cost in Watt-hours")
    battery_before_joules: float = Field(..., ge=0.0)
    battery_after_joules: float = Field(...)
    required_reserve_joules: float = Field(..., ge=0.0)
    reserve_feasible: bool = Field(..., description="Whether post-action return reserve was satisfied")
    estimated_benefit: float = Field(..., description="Expected mission benefit score")
    reason: str = Field(..., description="Explainable reason for selection or rejection")
    simulated_outcome: str = Field(
        ...,
        description="Labelled outcome description (e.g. '[SIMULATED] candidate inspected')"
    )
    provenance: DataProvenance = Field(
        default=DataProvenance.SIMULATED,
        description="Provenance classification of the decision outcome"
    )
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class DecisionLedger:
    """Audit ledger maintaining sequential history of all ARES policy evaluations."""

    def __init__(self):
        self._records: List[DecisionRecord] = []

    def record_decision(
        self,
        candidate_id: str,
        policy_id: str,
        selected_action: ActionType,
        action_energy_joules: float,
        battery_before_joules: float,
        battery_after_joules: float,
        required_reserve_joules: float,
        reserve_feasible: bool,
        estimated_benefit: float,
        reason: str,
        simulated_outcome: str,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> DecisionRecord:
        """Appends a new decision record to the ledger."""
        record_idx = len(self._records) + 1
        decision_id = f"dec_{policy_id.lower()}_{record_idx:04d}"
        
        # Ensure simulated outcomes are clearly labeled
        outcome_str = simulated_outcome
        if not outcome_str.startswith("[SIMULATED]") and not outcome_str.startswith("[ASSUMED]"):
            outcome_str = f"[SIMULATED] {outcome_str}"

        record = DecisionRecord(
            decision_id=decision_id,
            candidate_id=candidate_id,
            policy_id=policy_id,
            selected_action=selected_action,
            action_energy_joules=action_energy_joules,
            action_energy_wh=round(joules_to_wh(action_energy_joules), 4),
            battery_before_joules=battery_before_joules,
            battery_after_joules=battery_after_joules,
            required_reserve_joules=required_reserve_joules,
            reserve_feasible=reserve_feasible,
            estimated_benefit=estimated_benefit,
            reason=reason,
            simulated_outcome=outcome_str,
            provenance=DataProvenance.SIMULATED,
            extra_metadata=extra_metadata or {}
        )
        self._records.append(record)
        return record

    @property
    def records(self) -> List[DecisionRecord]:
        """Returns shallow copy of all logged records."""
        return list(self._records)

    def total_energy_spent_joules(self) -> float:
        """Calculates total energy expended across all feasible executed actions."""
        return sum(
            rec.action_energy_joules
            for rec in self._records
            if rec.reserve_feasible and rec.selected_action not in (ActionType.NONE, ActionType.RETURN_HOME)
        )

    def count_by_action(self) -> Dict[str, int]:
        """Summarizes action counts."""
        counts: Dict[str, int] = {}
        for rec in self._records:
            name = rec.selected_action.value
            counts[name] = counts.get(name, 0) + 1
        return counts
