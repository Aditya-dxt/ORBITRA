"""Action cost and outcome models for ARES.

Models three primary evidence-acquisition actions:
1. RECAPTURE: UAV physical flight, hover dwell, sensor capture, edge compute, and telemetry.
2. STRONGER_MODEL: Heavyweight inference model run on edge accelerator or server offload.
3. HUMAN_REVIEW: Queueing candidate for human analyst inspection (measuring queue capacity cost).

All energy values are in Joules. Parameter costs are tagged ASSUMED.
Simulated execution outcomes are tagged SIMULATED.
"""

from typing import NamedTuple, Optional
from pydantic import BaseModel, Field

from ares.energy.model import DroneEnergyModel, euclidean_distance
from ares.energy.units import joules_to_wh
from ares.schemas.candidate_state import ActionType, AresCandidateState
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


class RecaptureCostParameters(BaseModel):
    """Energy and timing parameters for UAV physical recapture."""
    hover_duration_sec: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=10.0,
            provenance=DataProvenance.ASSUMED,
            notes="Dwell hover duration over candidate in seconds"
        )
    )
    sensor_capture_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=450.0,
            provenance=DataProvenance.ASSUMED,
            notes="Camera gimbal + sensor burst capture energy (J)"
        )
    )
    edge_compute_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=350.0,
            provenance=DataProvenance.ASSUMED,
            notes="Baseline on-drone inference verification energy (J)"
        )
    )
    comms_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=120.0,
            provenance=DataProvenance.ASSUMED,
            notes="RF packet telemetry and thumbnail transmission energy (J)"
        )
    )


class StrongerModelCostParameters(BaseModel):
    """Energy and timing parameters for running a high-capacity specialist model."""
    compute_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=1200.0,
            provenance=DataProvenance.ASSUMED,
            notes="High-capacity VLM / dual-encoder inference energy on edge accelerator (J)"
        )
    )
    comms_offload_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=250.0,
            provenance=DataProvenance.ASSUMED,
            notes="Transmission energy if offloaded to server/ground station (J)"
        )
    )
    inference_duration_sec: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=2.5,
            provenance=DataProvenance.ASSUMED,
            notes="Elapsed inference latency in seconds"
        )
    )


class HumanReviewCostParameters(BaseModel):
    """Resource costs for queuing a candidate to a human analyst / pilot in command."""
    comms_alert_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=50.0,
            provenance=DataProvenance.ASSUMED,
            notes="Telemetry transmission energy for alert packet (J)"
        )
    )
    review_capacity_units: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=1.0,
            provenance=DataProvenance.ASSUMED,
            notes="Human review queue capacity slot (1.0 slot per candidate)"
        )
    )
    expected_latency_sec: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=180.0,
            provenance=DataProvenance.ASSUMED,
            notes="Expected human review turnaround time in seconds"
        )
    )


class ActionCostEstimate(BaseModel):
    """Projected energy, time, and capacity cost for a candidate verification action."""
    action_type: ActionType
    energy_cost_joules: float = Field(..., ge=0.0)
    energy_cost_wh: float = Field(..., ge=0.0)
    duration_sec: float = Field(..., ge=0.0)
    human_capacity_units: float = Field(default=0.0, ge=0.0)
    is_flight_action: bool = Field(..., description="True if requires UAV transit flight")
    notes: str
    provenance: DataProvenance = DataProvenance.ASSUMED


class SimulatedActionOutcome(BaseModel):
    """Simulated outcome resulting from executing an action in the simulator."""
    action_type: ActionType
    candidate_id: str
    prior_confidence: float
    post_confidence: float
    prior_uncertainty: float
    post_uncertainty: float
    delta_uncertainty: float
    outcome_summary: str
    provenance: DataProvenance = DataProvenance.SIMULATED


class ActionCostModel:
    """Calculates projected energy, duration, and capacity costs for actions."""

    def __init__(
        self,
        energy_model: Optional[DroneEnergyModel] = None,
        recapture_params: Optional[RecaptureCostParameters] = None,
        stronger_model_params: Optional[StrongerModelCostParameters] = None,
        human_review_params: Optional[HumanReviewCostParameters] = None
    ):
        self.energy_model = energy_model or DroneEnergyModel()
        self.recapture_params = recapture_params or RecaptureCostParameters()
        self.stronger_params = stronger_model_params or StrongerModelCostParameters()
        self.human_params = human_review_params or HumanReviewCostParameters()

    def estimate_cost(
        self,
        action: ActionType,
        current_pos: LocalGridCoordinates,
        target_pos: LocalGridCoordinates
    ) -> ActionCostEstimate:
        """Estimates resource expenditures in Joules, seconds, and capacity units."""
        if action == ActionType.RECAPTURE:
            dist = euclidean_distance(current_pos, target_pos)
            v = self.energy_model.params.nominal_speed_mps.value
            flight_time = dist / v
            flight_energy = self.energy_model.transit_energy_joules(current_pos, target_pos)
            
            hover_time = self.recapture_params.hover_duration_sec.value
            hover_energy = self.energy_model.hover_energy_joules(hover_time)
            
            capture_energy = self.recapture_params.sensor_capture_energy_joules.value
            compute_energy = self.recapture_params.edge_compute_energy_joules.value
            comms_energy = self.recapture_params.comms_energy_joules.value
            
            total_energy = flight_energy + hover_energy + capture_energy + compute_energy + comms_energy
            total_time = flight_time + hover_time + 1.0  # +1s for capture/compute
            
            return ActionCostEstimate(
                action_type=action,
                energy_cost_joules=round(total_energy, 1),
                energy_cost_wh=round(joules_to_wh(total_energy), 3),
                duration_sec=round(total_time, 1),
                human_capacity_units=0.0,
                is_flight_action=True,
                notes=(
                    f"Recapture sortie over {dist:.1f}m: flight={flight_energy:.1f}J, "
                    f"hover={hover_energy:.1f}J, sensor={capture_energy:.1f}J, "
                    f"compute={compute_energy:.1f}J, comms={comms_energy:.1f}J"
                ),
                provenance=DataProvenance.ASSUMED
            )

        elif action == ActionType.STRONGER_MODEL:
            # Stronger model consumes zero UAV flight or hover energy
            compute_energy = self.stronger_params.compute_energy_joules.value
            offload_energy = self.stronger_params.comms_offload_energy_joules.value
            total_energy = compute_energy + offload_energy
            duration = self.stronger_params.inference_duration_sec.value

            return ActionCostEstimate(
                action_type=action,
                energy_cost_joules=round(total_energy, 1),
                energy_cost_wh=round(joules_to_wh(total_energy), 3),
                duration_sec=duration,
                human_capacity_units=0.0,
                is_flight_action=False,
                notes=f"Heavyweight inference: compute={compute_energy:.1f}J, offload={offload_energy:.1f}J (zero flight energy)",
                provenance=DataProvenance.ASSUMED
            )

        elif action == ActionType.HUMAN_REVIEW:
            # Human review consumes negligible drone energy (just alert packet)
            alert_energy = self.human_params.comms_alert_energy_joules.value
            capacity = self.human_params.review_capacity_units.value
            duration = self.human_params.expected_latency_sec.value

            return ActionCostEstimate(
                action_type=action,
                energy_cost_joules=round(alert_energy, 1),
                energy_cost_wh=round(joules_to_wh(alert_energy), 4),
                duration_sec=duration,
                human_capacity_units=capacity,
                is_flight_action=False,
                notes="Queueing candidate for human analyst review; charges human capacity slot",
                provenance=DataProvenance.ASSUMED
            )

        else:
            return ActionCostEstimate(
                action_type=action,
                energy_cost_joules=0.0,
                energy_cost_wh=0.0,
                duration_sec=0.0,
                human_capacity_units=0.0,
                is_flight_action=False,
                notes=f"Zero-cost baseline action {action.value}",
                provenance=DataProvenance.ASSUMED
            )


class ActionOutcomeSimulator:
    """Generates synthetic simulated outcomes when actions are executed in simulation.
    
    RULE: All generated results are clearly marked [SIMULATED] and tagged SIMULATED.
    They must never be presented as physical drone measurements.
    """

    def simulate_outcome(
        self,
        action: ActionType,
        candidate_state: AresCandidateState,
        simulated_ground_truth_change: Optional[bool] = None
    ) -> SimulatedActionOutcome:
        """Simulates resolution of ambiguity based on action type."""
        prior_u = candidate_state.detection.uncertainty
        prior_c = candidate_state.detection.confidence

        if action == ActionType.RECAPTURE:
            # Physical recapture provides high-resolution view: cuts uncertainty by ~70%
            post_u = round(max(0.05, prior_u * 0.30), 3)
            # Confidence moves closer to definitive ground truth (or polarizes)
            if simulated_ground_truth_change is True:
                post_c = round(min(0.99, prior_c + (1.0 - prior_c) * 0.7), 3)
            elif simulated_ground_truth_change is False:
                post_c = round(max(0.01, prior_c * 0.3), 3)
            else:
                post_c = round(prior_c, 3)

            summary = (
                f"[SIMULATED] Recapture sortie completed: uncertainty reduced "
                f"from {prior_u:.2f} to {post_u:.2f} (Δu = {prior_u - post_u:+.2f})"
            )

        elif action == ActionType.STRONGER_MODEL:
            # Stronger model cuts uncertainty by ~40%
            post_u = round(max(0.10, prior_u * 0.60), 3)
            post_c = round(prior_c, 3)
            summary = (
                f"[SIMULATED] Specialist model inference completed: uncertainty reduced "
                f"from {prior_u:.2f} to {post_u:.2f} (Δu = {prior_u - post_u:+.2f})"
            )

        elif action == ActionType.HUMAN_REVIEW:
            # Human review conclusively resolves uncertainty (near zero)
            post_u = 0.02
            if simulated_ground_truth_change is not None:
                post_c = 1.0 if simulated_ground_truth_change else 0.0
            else:
                post_c = 1.0 if prior_c >= 0.5 else 0.0
            summary = (
                f"[SIMULATED] Human analyst triage completed: uncertainty resolved "
                f"to {post_u:.2f}; verified label assigned"
            )

        else:
            post_u = prior_u
            post_c = prior_c
            summary = f"[SIMULATED] No state modification for action {action.value}"

        return SimulatedActionOutcome(
            action_type=action,
            candidate_id=candidate_state.detection.candidate_id,
            prior_confidence=prior_c,
            post_confidence=post_c,
            prior_uncertainty=prior_u,
            post_uncertainty=post_u,
            delta_uncertainty=round(prior_u - post_u, 3),
            outcome_summary=summary,
            provenance=DataProvenance.SIMULATED
        )
