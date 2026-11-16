"""Abstract base policy interface for ARES."""

from abc import ABC, abstractmethod
from typing import List

from ares.schemas.candidate_state import AresCandidateState, CandidateStatus


class BasePolicy(ABC):
    """Abstract base class for all ARES candidate scheduling and action policies."""

    def __init__(self, policy_id: str, policy_name: str):
        self.policy_id = policy_id
        self.policy_name = policy_name

    @abstractmethod
    def rank_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """Ranks pending candidates according to the policy's prioritization rules."""
        pass

    @abstractmethod
    def evaluate_benefit(self, candidate: AresCandidateState) -> float:
        """Calculates expected mission benefit for inspecting this candidate."""
        pass

    def get_pending_candidates(
        self,
        candidates: List[AresCandidateState]
    ) -> List[AresCandidateState]:
        """Filters candidates whose lifecycle status is PENDING."""
        return [c for c in candidates if c.status == CandidateStatus.PENDING]
