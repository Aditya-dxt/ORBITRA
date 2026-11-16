"""B0: Fixed Pass Policy.

Processes candidates in a predetermined sequential order (e.g. discovery order)
without re-ranking based on uncertainty or importance.
"""

from typing import List

from ares.policies.base import BasePolicy
from ares.schemas.candidate_state import AresCandidateState


class B0FixedPassPolicy(BasePolicy):
    """B0: Fixed pass baseline policy."""

    def __init__(self):
        super().__init__(
            policy_id="B0",
            policy_name="Fixed Pass"
        )

    def rank_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """Preserves the original predetermined input ordering of pending candidates."""
        return self.get_pending_candidates(candidates)

    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Evaluates nominal benefit based on detection confidence and importance weight.
        
        Formula (starting assumption):
            Benefit = importance_weight * confidence
        """
        weight = float(candidate.importance_weight.value)
        conf = candidate.detection.confidence
        return round(weight * conf, 4)
