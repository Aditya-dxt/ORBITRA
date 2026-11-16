"""B1: Uncertainty First Policy.

Prioritizes candidates with the highest detector uncertainty first,
aiming to reduce operational ambiguity where information gain is greatest.
"""

from typing import List

from ares.policies.base import BasePolicy
from ares.schemas.candidate_state import AresCandidateState


class B1UncertaintyFirstPolicy(BasePolicy):
    """B1: Uncertainty First prioritization policy."""

    def __init__(self):
        super().__init__(
            policy_id="B1",
            policy_name="Uncertainty First"
        )

    def rank_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """Ranks pending candidates descending by uncertainty, breaking ties with importance weight."""
        pending = self.get_pending_candidates(candidates)
        return sorted(
            pending,
            key=lambda c: (
                c.detection.uncertainty,
                float(c.importance_weight.value)
            ),
            reverse=True
        )

    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Evaluates benefit based on uncertainty reduction weighted by importance.
        
        Formula (starting assumption):
            Benefit = importance_weight * uncertainty
        """
        weight = float(candidate.importance_weight.value)
        unc = candidate.detection.uncertainty
        return round(weight * unc, 4)
