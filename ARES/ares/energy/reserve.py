"""Return-reserve rule and safety guardrail engine.

Enforces:
1. Return energy evaluated from the position AFTER the action back to home base.
2. Exactly one uncertainty allowance (reserve_uncertainty_margin) to prevent double-counting.
3. Explicit separate wind margin parameter (wind_margin_joules).
All units strictly in Joules.
"""

from typing import NamedTuple, Optional
from pydantic import BaseModel, Field

from ares.energy.model import DroneEnergyModel, euclidean_distance
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


class ReturnReserveConfig(BaseModel):
    """Configuration for safe-return reserve calculations."""
    reserve_uncertainty_margin: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.20,
            provenance=DataProvenance.ASSUMED,
            notes="Single 20% return-reserve uncertainty multiplier (prevents double-counting)"
        )
    )
    wind_margin_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=1200.0,
            provenance=DataProvenance.ASSUMED,
            notes="Explicit additive margin in Joules for headwind/gust compensation"
        )
    )


class ReserveCheckResult(NamedTuple):
    """Result of evaluating a proposed action against the return-reserve constraint."""
    is_feasible: bool
    remaining_after_action_joules: float
    required_reserve_joules: float
    nominal_return_energy_joules: float
    post_action_distance_to_home_m: float
    reason: str


class ReturnReserveCalculator:
    """Evaluates safe-return reserve feasibility for proposed drone actions."""

    def __init__(
        self,
        energy_model: Optional[DroneEnergyModel] = None,
        config: Optional[ReturnReserveConfig] = None
    ):
        self.energy_model = energy_model or DroneEnergyModel()
        self.config = config or ReturnReserveConfig()

    def calculate_nominal_return_energy_joules(
        self,
        post_action_pos: LocalGridCoordinates,
        home_pos: LocalGridCoordinates
    ) -> float:
        """Calculates nominal transit flight energy in Joules from post-action position back to home base."""
        return self.energy_model.transit_energy_joules(post_action_pos, home_pos)

    def calculate_required_reserve_joules(
        self,
        post_action_pos: LocalGridCoordinates,
        home_pos: LocalGridCoordinates
    ) -> float:
        """Calculates total protected return reserve in Joules.
        
        Formula:
            E_reserve = (1.0 + reserve_uncertainty_margin) * E_return_nominal + wind_margin_joules
        """
        e_nominal = self.calculate_nominal_return_energy_joules(post_action_pos, home_pos)
        margin_pct = self.config.reserve_uncertainty_margin.value
        wind_j = self.config.wind_margin_joules.value
        return (1.0 + margin_pct) * e_nominal + wind_j

    def check_action_feasibility(
        self,
        current_battery_joules: float,
        estimated_action_joules: float,
        post_action_pos: LocalGridCoordinates,
        home_pos: LocalGridCoordinates
    ) -> ReserveCheckResult:
        """Evaluates whether executing the action leaves sufficient battery to guarantee safe return.
        
        The post-action position is used for calculating the return energy.
        """
        nominal_return = self.calculate_nominal_return_energy_joules(post_action_pos, home_pos)
        required_reserve = self.calculate_required_reserve_joules(post_action_pos, home_pos)
        dist_home = euclidean_distance(post_action_pos, home_pos)
        
        remaining_after_action = current_battery_joules - estimated_action_joules
        
        if remaining_after_action < 0.0:
            return ReserveCheckResult(
                is_feasible=False,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                post_action_distance_to_home_m=dist_home,
                reason=f"Action cost ({estimated_action_joules:.1f} J) exceeds current battery ({current_battery_joules:.1f} J)"
            )

        if remaining_after_action >= required_reserve:
            return ReserveCheckResult(
                is_feasible=True,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                post_action_distance_to_home_m=dist_home,
                reason="Battery after action satisfies post-action return reserve"
            )
        else:
            return ReserveCheckResult(
                is_feasible=False,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                post_action_distance_to_home_m=dist_home,
                reason=(
                    f"Remaining battery ({remaining_after_action:.1f} J) violates required "
                    f"return reserve ({required_reserve:.1f} J) from post-action location"
                )
            )
