"""Candidate state tracking and lifecycle management in ARES.

Separates ARES-owned decision and mission fields from SatQuery detection inputs.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import SatQueryCandidateRecord


class CandidateStatus(str, Enum):
    """Lifecycle status of a change candidate inside ARES."""
    PENDING = "PENDING"       # Ingested, awaiting policy action selection
    INSPECTED = "INSPECTED"   # Selected action executed
    DEFERRED = "DEFERRED"     # Postponed due to energy/reserve guardrail
    SKIPPED = "SKIPPED"       # Bypassed by policy


class ActionType(str, Enum):
    """Actions that ARES can allocate to a candidate."""
    NONE = "NONE"
    RECAPTURE = "RECAPTURE"                     # UAV sortie to re-image region
    STRONGER_MODEL = "STRONGER_MODEL"           # Heavyweight inference pipeline
    HUMAN_REVIEW = "HUMAN_REVIEW"               # Queue for human analyst triage
    RETURN_HOME = "RETURN_HOME"                 # Transit back to base


class ImportanceTier(float, Enum):
    """Configurable starting importance weights: 1.0 (Low), 2.0 (Med), 4.0 (High)."""
    LOW = 1.0
    MEDIUM = 2.0
    HIGH = 4.0


class EvidenceRecord(BaseModel):
    """Audit entry recording verification action execution and simulated outcome."""
    action: ActionType
    timestamp: str
    energy_spent_joules: float = Field(..., ge=0.0)
    simulated_outcome: str = Field(
        ...,
        description="Must be labeled with SIMULATED outcome descriptor"
    )
    notes: Optional[str] = None


class AresCandidateState(BaseModel):
    """Complete candidate state combining SatQuery input with ARES mission fields."""
    detection: SatQueryCandidateRecord
    
    # ARES-owned fields:
    importance_weight: ProvenanceValue[float] = Field(
        default_factory=lambda: ProvenanceValue(
            value=ImportanceTier.MEDIUM.value,
            provenance=DataProvenance.ASSUMED,
            notes="Starting assumption weight (1, 2, or 4)"
        )
    )
    status: CandidateStatus = Field(default=CandidateStatus.PENDING)
    assigned_action: ActionType = Field(default=ActionType.NONE)
    estimated_benefit: float = Field(default=0.0)
    estimated_energy_joules: float = Field(default=0.0)
    reserve_feasible: Optional[bool] = Field(default=None)
    decision_reason: Optional[str] = Field(default=None)
    evidence_history: List[EvidenceRecord] = Field(default_factory=list)

    def set_importance(self, tier: ImportanceTier) -> None:
        """Sets the mission importance weight with ASSUMED provenance tag."""
        self.importance_weight = ProvenanceValue(
            value=tier.value,
            provenance=DataProvenance.ASSUMED,
            notes=f"Assigned {tier.name} priority ({tier.value})"
        )
