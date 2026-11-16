"""Synthetic SatQuery candidate generator for testing and simulation milestones.

RULE: All generated records are synthetic mock data and are explicitly marked
as [SYNTHETIC EXAMPLE] to avoid confusion with real SatQuery vision outputs.
"""

from typing import List
from ares.schemas.candidate_state import AresCandidateState, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)


def generate_synthetic_candidate_records() -> List[SatQueryCandidateRecord]:
    """Generates a reproducible set of synthetic candidate change records for simulation."""
    return [
        SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_synth_001",
            image_pair_id="pair_synth_cartosat_risat_01",
            timestamp="2026-11-16T09:00:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] flooded_cropland",
            confidence=0.88,
            uncertainty=0.72,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=250.0, y_meters=180.0, z_meters=50.0),
                bbox_pixels=[100, 100, 150, 150]
            )
        ),
        SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_synth_002",
            image_pair_id="pair_synth_cartosat_risat_01",
            timestamp="2026-11-16T09:01:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] new_construction",
            confidence=0.94,
            uncertainty=0.25,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=420.0, y_meters=310.0, z_meters=60.0),
                bbox_pixels=[200, 180, 270, 240]
            )
        ),
        SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_synth_003",
            image_pair_id="pair_synth_cartosat_risat_01",
            timestamp="2026-11-16T09:02:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] road_obstruction",
            confidence=0.65,
            uncertainty=0.85,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=600.0, y_meters=500.0, z_meters=55.0),
                bbox_pixels=[310, 420, 380, 490]
            )
        ),
        SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_synth_004",
            image_pair_id="pair_synth_cartosat_risat_01",
            timestamp="2026-11-16T09:03:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] vegetation_clearance",
            confidence=0.82,
            uncertainty=0.48,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=850.0, y_meters=700.0, z_meters=70.0),
                bbox_pixels=[400, 50, 480, 130]
            )
        ),
        SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id="cand_synth_005",
            image_pair_id="pair_synth_cartosat_risat_01",
            timestamp="2026-11-16T09:04:00Z",
            predicted_change="[SYNTHETIC EXAMPLE] industrial_spill",
            confidence=0.55,
            uncertainty=0.91,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=1100.0, y_meters=950.0, z_meters=80.0),
                bbox_pixels=[50, 300, 130, 390]
            )
        ),
    ]


def create_synthetic_candidate_states() -> List[AresCandidateState]:
    """Wraps synthetic detections into AresCandidateState with configured starting importance tiers."""
    records = generate_synthetic_candidate_records()
    states = []
    
    # Starting importance weights: 1.0 (Low), 2.0 (Med), 4.0 (High)
    tiers = [
        ImportanceTier.HIGH,
        ImportanceTier.LOW,
        ImportanceTier.HIGH,
        ImportanceTier.MEDIUM,
        ImportanceTier.HIGH,
    ]
    
    for rec, tier in zip(records, tiers):
        state = AresCandidateState(
            detection=rec,
            importance_weight=ProvenanceValue(
                value=tier.value,
                provenance=DataProvenance.ASSUMED,
                notes=f"Synthetic assignment: {tier.name} priority ({tier.value})"
            )
        )
        states.append(state)
        
    return states
