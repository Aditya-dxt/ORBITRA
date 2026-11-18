"""Unit tests for mission importance scoring and decoupling from confidence.

Updated to reflect agreed provisional interface (v1.0.0):
uncertainty is normalized binary Shannon entropy of confidence:
    u = -[p*log2(p) + (1-p)*log2(1-p)]
Test records compute uncertainty from confidence to satisfy the cross-check.
"""

import math
import unittest

from ares.schemas.candidate_state import AresCandidateState, ImportanceTier
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from ares.scoring.importance import ImportanceScorer, ImportanceScoringConfig


def _entropy(p: float) -> float:
    """Binary Shannon entropy -- agreed uncertainty formula."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return round(-(p * math.log2(p) + (1 - p) * math.log2(1 - p)), 4)


class TestImportanceScoring(unittest.TestCase):
    """Verifies importance scoring rules, zone multipliers, and decoupling from confidence."""

    def _make_candidate(self, predicted_change: str, confidence: float) -> SatQueryCandidateRecord:
        """Creates a [SYNTHETIC EXAMPLE] record with formula-consistent uncertainty.

        uncertainty is computed as Shannon entropy of confidence to satisfy the
        agreed cross-check in SatQueryCandidateRecord (tolerance +/-0.15).
        """
        return SatQueryCandidateRecord(
            schema_version="v1.0.0",
            candidate_id="cand_test_scoring",
            image_pair_id="pair_01",
            timestamp="2026-11-16T09:00:00Z",
            predicted_change=predicted_change,
            confidence=confidence,
            uncertainty=_entropy(confidence),  # formula-consistent: u = h(confidence)
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)
            )
        )

    def test_decoupling_confidence_from_importance(self):
        scorer = ImportanceScorer()

        # High confidence, but low priority category (ordinary new construction)
        c_low = self._make_candidate("new_construction", confidence=0.98)
        # Low confidence, but high priority category (industrial spill)
        c_high = self._make_candidate("industrial_spill", confidence=0.45)

        score_low = scorer.evaluate_importance(c_low)
        score_high = scorer.evaluate_importance(c_high)

        # Importance reflects mission priority, NOT detector confidence!
        self.assertEqual(score_low.value, ImportanceTier.LOW.value)    # 1.0
        self.assertEqual(score_high.value, ImportanceTier.HIGH.value)  # 4.0
        self.assertGreater(score_high.value, score_low.value)
        self.assertEqual(score_low.provenance, DataProvenance.ASSUMED)
        self.assertEqual(score_high.provenance, DataProvenance.ASSUMED)

    def test_zone_multiplier(self):
        scorer = ImportanceScorer()
        c = self._make_candidate("flooded_cropland", confidence=0.80)  # Base weight 2.0

        # Standard zone (1.0x) -> 2.0
        score_standard = scorer.evaluate_importance(c, zone_id="standard_zone")
        self.assertEqual(score_standard.value, 2.0)

        # Protected reserve (1.5x) -> 3.0
        score_protected = scorer.evaluate_importance(c, zone_id="protected_reserve")
        self.assertEqual(score_protected.value, 3.0)

        # Defence buffer (2.0x) -> 4.0
        score_defence = scorer.evaluate_importance(c, zone_id="defence_buffer")
        self.assertEqual(score_defence.value, 4.0)

    def test_unknown_category_fallback(self):
        scorer = ImportanceScorer(config=ImportanceScoringConfig(default_weight=2.0))
        c = self._make_candidate("unrecognized_alien_monolith", confidence=0.75)
        score = scorer.evaluate_importance(c)
        self.assertEqual(score.value, 2.0)

    def test_apply_to_candidate_state(self):
        scorer = ImportanceScorer()
        c = self._make_candidate("government_land_encroachment", confidence=0.82)
        state = AresCandidateState(detection=c)

        self.assertEqual(state.importance_weight.value, ImportanceTier.MEDIUM.value)  # default before scoring
        scorer.apply_to_candidate_state(state)
        self.assertEqual(state.importance_weight.value, ImportanceTier.HIGH.value)    # 4.0 after scoring


if __name__ == "__main__":
    unittest.main()
