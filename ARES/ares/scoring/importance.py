"""Mission importance scoring model for ARES.

Decouples operational mission priority from vision detector confidence.
All weights, categories, and multiplier rules are starting assumptions tagged ASSUMED.
"""

from typing import Dict, Optional
from pydantic import BaseModel, Field

from ares.schemas.candidate_state import AresCandidateState, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import SatQueryCandidateRecord


class ImportanceScoringConfig(BaseModel):
    """Configuration mapping predicted change classes and zones to importance weights."""
    
    # Base weight tier assignments (Low=1.0, Medium=2.0, High=4.0)
    category_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            # High priority: government land, water bodies, high-consequence hazards
            "government_land_encroachment": ImportanceTier.HIGH.value,
            "industrial_spill": ImportanceTier.HIGH.value,
            "water_body_change": ImportanceTier.HIGH.value,
            "critical_infrastructure": ImportanceTier.HIGH.value,
            "[synthetic example] industrial_spill": ImportanceTier.HIGH.value,
            
            # Medium priority: agricultural flooding, clearance, road obstruction
            "flooded_cropland": ImportanceTier.MEDIUM.value,
            "vegetation_clearance": ImportanceTier.MEDIUM.value,
            "road_obstruction": ImportanceTier.MEDIUM.value,
            "[synthetic example] flooded_cropland": ImportanceTier.MEDIUM.value,
            "[synthetic example] road_obstruction": ImportanceTier.MEDIUM.value,
            "[synthetic example] vegetation_clearance": ImportanceTier.MEDIUM.value,
            
            # Low priority: ordinary new construction, seasonal shifts, rural land
            "new_construction": ImportanceTier.LOW.value,
            "seasonal_vegetation": ImportanceTier.LOW.value,
            "ordinary_land": ImportanceTier.LOW.value,
            "[synthetic example] new_construction": ImportanceTier.LOW.value,
        }
    )
    
    # Default weight if category is not recognized
    default_weight: float = Field(default=ImportanceTier.MEDIUM.value)
    
    # Optional zone multiplier (e.g., 1.5x for strict protected conservation zones)
    zone_multipliers: Dict[str, float] = Field(
        default_factory=lambda: {
            "protected_reserve": 1.5,
            "defence_buffer": 2.0,
            "standard_zone": 1.0,
        }
    )


class ImportanceScorer:
    """Computes mission-importance scores decoupled from vision model confidence.
    
    NOTE: Importance scores represent operational priority (how much a change matters
    to human stakeholders), whereas model confidence represents statistical certainty
    (how sure the vision detector is that an optical difference exists).
    """

    def __init__(self, config: Optional[ImportanceScoringConfig] = None):
        self.config = config or ImportanceScoringConfig()

    def evaluate_importance(
        self,
        candidate: SatQueryCandidateRecord,
        zone_id: Optional[str] = None
    ) -> ProvenanceValue[float]:
        """Calculates the mission importance weight for a candidate change record."""
        category_key = candidate.predicted_change.strip().lower()
        base_weight = self.config.category_weights.get(category_key, self.config.default_weight)
        
        # Apply zone multiplier if applicable
        zone_mult = 1.0
        if zone_id:
            zone_mult = self.config.zone_multipliers.get(zone_id.strip().lower(), 1.0)
            
        final_weight = round(base_weight * zone_mult, 2)
        
        return ProvenanceValue(
            value=final_weight,
            provenance=DataProvenance.ASSUMED,
            notes=(
                f"Assigned weight {final_weight} (base={base_weight}, zone_multiplier={zone_mult}) "
                f"for predicted_change='{candidate.predicted_change}'"
            )
        )

    def apply_to_candidate_state(
        self,
        state: AresCandidateState,
        zone_id: Optional[str] = None
    ) -> AresCandidateState:
        """Assigns the evaluated importance weight directly into the candidate state."""
        weight_with_provenance = self.evaluate_importance(state.detection, zone_id=zone_id)
        state.importance_weight = weight_with_provenance
        return state
