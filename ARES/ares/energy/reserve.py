"""Return-reserve rule and safety guardrail engine.

Enforces:
1. Return energy evaluated from the position AFTER the action back to home base.
2. Exactly one uncertainty allowance to prevent double-counting, supporting either:
   - Relative percentage allowance (e.g. 20% of return energy, corresponding to k=2 with 10% CoV)
   - Absolute standard deviation in Joules (k * sigma_E, e.g. k=2 * sigma_joules)
3. Explicit separate additive wind margin parameter (wind_margin_joules).
All units strictly in Joules. Assumptions are clearly tagged as ASSUMED.
"""

from typing import NamedTuple, Optional
from pydantic import BaseModel, Field

from ares.energy.model import DroneEnergyModel, euclidean_distance
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


class ReturnReserveConfig(BaseModel):
    """Configuration for safe-return reserve calculations."""
    
    # Coverage factor k (e.g. 2 standard deviations for ~95% confidence under normal distribution)
    k_coverage_factor: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=2.0,
            provenance=DataProvenance.ASSUMED,
            notes="Starting assumption coverage multiplier k=2"
        )
    )
    
    # Relative uncertainty fraction of nominal return energy (used when absolute sigma is not provided)
    # Default 0.20 (20%), reconciling k=2 with an assumed 10% coefficient of variation (k * 0.10 = 0.20)
    reserve_uncertainty_margin: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=0.20,
            provenance=DataProvenance.ASSUMED,
            notes="Default 20% relative return energy uncertainty allowance (reconciles k=2 with 10% CoV)"
        )
    )
    
    # Absolute standard deviation of return energy estimation in Joules (optional; if set, used as k * sigma_E)
    sigma_return_energy_joules: Optional[ProvenanceValue[float]] = Field(
        default=None,
        description="Optional absolute standard deviation in Joules. When provided, uncertainty allowance = k * sigma"
    )
    
    # Separate explicit additive margin for wind and adverse gusts in Joules
    wind_margin_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=1200.0,
            provenance=DataProvenance.ASSUMED,
            notes="Explicit additive margin in Joules for headwind/gust compensation (decoupled from uncertainty)"
        )
    )


class ReserveCheckResult(NamedTuple):
    """Result of evaluating a proposed action against the return-reserve constraint."""
    is_feasible: bool
    remaining_after_action_joules: float
    required_reserve_joules: float
    nominal_return_energy_joules: float
    uncertainty_allowance_joules: float
    wind_margin_joules: float
    post_action_distance_to_home_m: float
    reason: str


class ReturnReserveCalculator:
    """Evaluates safe-return reserve feasibility for proposed drone actions.
    
    NOTE: All safety margins and reserve requirements are model-based starting
    assumptions, NOT validated physical flight safety guarantees.
    """

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

    def calculate_uncertainty_allowance_joules(self, nominal_return_joules: float) -> float:
        """Calculates exactly one uncertainty allowance in Joules.
        
        If sigma_return_energy_joules is configured, uses:
            UncertaintyAllowance = k * sigma_E (Joules)
        Otherwise, uses relative return fraction:
            UncertaintyAllowance = reserve_uncertainty_margin * nominal_return_joules
        This guarantees no double-counting between standard deviation and percentage margins.
        """
        k = self.config.k_coverage_factor.value
        if self.config.sigma_return_energy_joules is not None and self.config.sigma_return_energy_joules.value > 0:
            sigma = self.config.sigma_return_energy_joules.value
            return k * sigma
        else:
            margin_pct = self.config.reserve_uncertainty_margin.value
            return margin_pct * nominal_return_joules

    def calculate_required_reserve_joules(
        self,
        post_action_pos: LocalGridCoordinates,
        home_pos: LocalGridCoordinates
    ) -> float:
        """Calculates total protected return reserve in Joules.
        
        Formula:
            E_reserve = E_return_nominal + UncertaintyAllowance + wind_margin_joules
        Where UncertaintyAllowance is evaluated using either k * sigma_E or relative margin (never both).
        """
        e_nominal = self.calculate_nominal_return_energy_joules(post_action_pos, home_pos)
        e_uncertainty = self.calculate_uncertainty_allowance_joules(e_nominal)
        wind_j = self.config.wind_margin_joules.value
        return e_nominal + e_uncertainty + wind_j

    def check_action_feasibility(
        self,
        current_battery_joules: float,
        estimated_action_joules: float,
        post_action_pos: LocalGridCoordinates,
        home_pos: LocalGridCoordinates
    ) -> ReserveCheckResult:
        """Evaluates whether executing the action leaves sufficient battery to guarantee safe return.
        
        The return energy is evaluated strictly from the position AFTER the action.
        """
        nominal_return = self.calculate_nominal_return_energy_joules(post_action_pos, home_pos)
        uncertainty_allowance = self.calculate_uncertainty_allowance_joules(nominal_return)
        wind_j = self.config.wind_margin_joules.value
        required_reserve = nominal_return + uncertainty_allowance + wind_j
        dist_home = euclidean_distance(post_action_pos, home_pos)
        
        remaining_after_action = current_battery_joules - estimated_action_joules
        
        if remaining_after_action < 0.0:
            return ReserveCheckResult(
                is_feasible=False,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                uncertainty_allowance_joules=uncertainty_allowance,
                wind_margin_joules=wind_j,
                post_action_distance_to_home_m=dist_home,
                reason=f"Action cost ({estimated_action_joules:.1f} J) exceeds current battery ({current_battery_joules:.1f} J)"
            )

        if remaining_after_action >= required_reserve:
            return ReserveCheckResult(
                is_feasible=True,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                uncertainty_allowance_joules=uncertainty_allowance,
                wind_margin_joules=wind_j,
                post_action_distance_to_home_m=dist_home,
                reason="Battery after action satisfies post-action return reserve"
            )
        else:
            return ReserveCheckResult(
                is_feasible=False,
                remaining_after_action_joules=remaining_after_action,
                required_reserve_joules=required_reserve,
                nominal_return_energy_joules=nominal_return,
                uncertainty_allowance_joules=uncertainty_allowance,
                wind_margin_joules=wind_j,
                post_action_distance_to_home_m=dist_home,
                reason=(
                    f"Remaining battery ({remaining_after_action:.1f} J) violates required "
                    f"return reserve ({required_reserve:.1f} J) from post-action location"
                )
            )
