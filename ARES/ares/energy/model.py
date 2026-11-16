"""UAV kinematics and action energy cost model.

All calculations and stored quantities are in Joules.
Starting assumptions (k=2, aerodynamic power scaling, hardware draws)
are tagged as ASSUMED.
"""

import math
from typing import Optional
from pydantic import BaseModel, Field

from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import LocalGridCoordinates


class DroneEnergyParameters(BaseModel):
    """Configurable physical and hardware energy parameters."""
    nominal_speed_mps: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=12.0,
            provenance=DataProvenance.ASSUMED,
            notes="Nominal cruising flight speed (m/s)"
        )
    )
    flight_power_watts: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=180.0,
            provenance=DataProvenance.ASSUMED,
            notes="Nominal aerodynamic cruising electrical power draw (W)"
        )
    )
    hover_power_watts: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=220.0,
            provenance=DataProvenance.ASSUMED,
            notes="Hovering electrical power draw (W)"
        )
    )
    sensor_capture_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=450.0,
            provenance=DataProvenance.ASSUMED,
            notes="Energy per multispectral/optical burst capture sequence (J)"
        )
    )
    compute_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=350.0,
            provenance=DataProvenance.ASSUMED,
            notes="Onboard edge inference energy for baseline verification (J)"
        )
    )
    comms_energy_joules: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=120.0,
            provenance=DataProvenance.ASSUMED,
            notes="Telemetry and compressed frame packet transmission energy (J)"
        )
    )
    k_drag_exponent: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=2.0,
            provenance=DataProvenance.ASSUMED,
            notes="Configurable aerodynamic drag exponent starting assumption k=2"
        )
    )


def euclidean_distance(p1: LocalGridCoordinates, p2: LocalGridCoordinates) -> float:
    """Calculates 3D Euclidean distance in meters between two local grid coordinates."""
    dx = p1.x_meters - p2.x_meters
    dy = p1.y_meters - p2.y_meters
    dz = p1.z_meters - p2.z_meters
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class DroneEnergyModel:
    """Calculates energy expenditure in Joules for drone navigation and actions."""

    def __init__(self, params: Optional[DroneEnergyParameters] = None):
        self.params = params or DroneEnergyParameters()

    def transit_energy_joules(
        self,
        from_pos: LocalGridCoordinates,
        to_pos: LocalGridCoordinates,
        speed_mps: Optional[float] = None
    ) -> float:
        """Calculates transit cruise flight energy in Joules between two waypoints."""
        v = speed_mps or self.params.nominal_speed_mps.value
        if v <= 0:
            raise ValueError(f"Speed must be positive, got {v} m/s")
        dist_m = euclidean_distance(from_pos, to_pos)
        transit_time_sec = dist_m / v
        power_w = self.params.flight_power_watts.value
        return power_w * transit_time_sec

    def hover_energy_joules(self, duration_sec: float) -> float:
        """Calculates energy spent hovering in Joules."""
        if duration_sec < 0:
            raise ValueError(f"Hover duration cannot be negative: {duration_sec}")
        return self.params.hover_power_watts.value * duration_sec

    def estimate_recapture_action_energy(
        self,
        current_pos: LocalGridCoordinates,
        target_pos: LocalGridCoordinates,
        hover_sec: float = 10.0
    ) -> float:
        """Estimates total energy in Joules to fly to candidate, hover, capture, compute, and transmit."""
        e_transit = self.transit_energy_joules(current_pos, target_pos)
        e_hover = self.hover_energy_joules(hover_sec)
        e_capture = self.params.sensor_capture_energy_joules.value
        e_compute = self.params.compute_energy_joules.value
        e_comms = self.params.comms_energy_joules.value
        return e_transit + e_hover + e_capture + e_compute + e_comms
