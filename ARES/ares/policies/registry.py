"""Policy registry and metadata catalog for ARES.

Maintains required policies B0-B4 and documents supplementary baselines P1, P2, P5.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel

from ares.policies.base import BasePolicy
from ares.policies.b0_fixed_pass import B0FixedPassPolicy
from ares.policies.b1_uncertainty_first import B1UncertaintyFirstPolicy
from ares.policies.b2_adaptive_computation import (
    B2AdaptiveComputationConfig,
    B2AdaptiveComputationPolicy,
)
from ares.policies.b3_joint_policy import (
    B3JointPolicyConfig,
    B3JointPolicy,
)
from ares.policies.b4_greedy_benefit_per_energy import (
    B4GreedyBenefitPerEnergyConfig,
    B4GreedyBenefitPerEnergyPolicy,
)


class PolicyStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PLANNED = "PLANNED"
    SUPPLEMENTARY_BASELINE = "SUPPLEMENTARY_BASELINE"


class PolicyMetadata(BaseModel):
    policy_id: str
    name: str
    description: str
    status: PolicyStatus
    notes: Optional[str] = None


POLICY_CATALOG: Dict[str, PolicyMetadata] = {
    "B0": PolicyMetadata(
        policy_id="B0",
        name="Fixed Pass",
        description="Processes candidates in predetermined sequence until return reserve mandates return.",
        status=PolicyStatus.IMPLEMENTED,
        notes="Primary baseline checkpoint."
    ),
    "B1": PolicyMetadata(
        policy_id="B1",
        name="Uncertainty First",
        description="Prioritizes candidates with highest detector uncertainty first.",
        status=PolicyStatus.IMPLEMENTED,
        notes="First adaptive prioritization policy checkpoint."
    ),
    "B2": PolicyMetadata(
        policy_id="B2",
        name="Adaptive Computation",
        description="Dynamically selects computation depth and verification modality per candidate.",
        status=PolicyStatus.IMPLEMENTED,
        notes="Adaptive compute policy checkpoint."
    ),
    "B3": PolicyMetadata(
        policy_id="B3",
        name="Joint Policy",
        description="Jointly selects target candidate and inspection/computation action level in a single objective evaluation.",
        status=PolicyStatus.IMPLEMENTED,
        notes="Implemented in Milestone 4."
    ),
    "B4": PolicyMetadata(
        policy_id="B4",
        name="Greedy Benefit per Energy",
        description="Prioritizes candidates maximizing marginal benefit per expended Joule (dB/dE) using RECAPTURE.",
        status=PolicyStatus.IMPLEMENTED,
        notes="Implemented in Milestone 5."
    ),
    "P1": PolicyMetadata(
        policy_id="P1",
        name="Confidence Ranked (Supplementary)",
        description="Prioritizes candidates strictly by vision detector confidence.",
        status=PolicyStatus.SUPPLEMENTARY_BASELINE,
        notes="Supplementary comparison baseline from project blueprint."
    ),
    "P2": PolicyMetadata(
        policy_id="P2",
        name="Importance Ranked (Supplementary)",
        description="Prioritizes candidates strictly by mission importance weight.",
        status=PolicyStatus.SUPPLEMENTARY_BASELINE,
        notes="Supplementary comparison baseline from project blueprint."
    ),
    "P5": PolicyMetadata(
        policy_id="P5",
        name="Zone-Weighted Spatial (Supplementary)",
        description="Prioritizes candidates weighted by geographic sector risk.",
        status=PolicyStatus.SUPPLEMENTARY_BASELINE,
        notes="Included as supplementary baseline only if zone weighting diverges from B4."
    ),
}


def get_policy(policy_id: str) -> BasePolicy:
    """Instantiates an implemented policy or raises NotImplementedError for planned ones."""
    pid = policy_id.upper()
    if pid == "B0":
        return B0FixedPassPolicy()
    elif pid == "B1":
        return B1UncertaintyFirstPolicy()
    elif pid == "B2":
        return B2AdaptiveComputationPolicy()
    elif pid == "B3":
        return B3JointPolicy()
    elif pid == "B4":
        return B4GreedyBenefitPerEnergyPolicy()
    elif pid in POLICY_CATALOG:
        meta = POLICY_CATALOG[pid]
        raise NotImplementedError(
            f"Policy {pid} ('{meta.name}') is currently {meta.status.value}. "
            f"Implemented policies in this milestone: B0, B1, B2, B3, B4."
        )
    else:
        raise KeyError(f"Unknown policy ID: {policy_id}. Available: {list(POLICY_CATALOG.keys())}")


def list_policies() -> List[PolicyMetadata]:
    """Returns list of all catalogued policies and their current status."""
    return list(POLICY_CATALOG.values())
