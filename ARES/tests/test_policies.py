"""Unit tests for ARES policies and registry catalog."""

import unittest

from ares.policies.b0_fixed_pass import B0FixedPassPolicy
from ares.policies.b1_uncertainty_first import B1UncertaintyFirstPolicy
from ares.policies.b2_adaptive_computation import B2AdaptiveComputationPolicy
from ares.policies.b3_joint_policy import B3JointPolicy
from ares.policies.registry import (
    POLICY_CATALOG,
    PolicyStatus,
    get_policy,
    list_policies,
)
from ares.schemas.candidate_state import AresCandidateState, ImportanceTier
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)


class TestPolicies(unittest.TestCase):
    """Verifies B0 (Fixed Pass), B1 (Uncertainty First), B2 (Adaptive Compute), B3 (Joint), and the policy registry."""

    def _create_candidate(self, cid: str, conf: float, unc: float, imp: ImportanceTier) -> AresCandidateState:
        record = SatQueryCandidateRecord(
            schema_version="v1.0.0-provisional",
            candidate_id=cid,
            image_pair_id="pair_test",
            timestamp="2026-11-16T09:00:00Z",
            predicted_change="test_change",
            confidence=conf,
            uncertainty=unc,
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(x_meters=100.0, y_meters=100.0, z_meters=50.0)
            )
        )
        state = AresCandidateState(
            detection=record,
            importance_weight=ProvenanceValue(
                value=imp.value,
                provenance=DataProvenance.ASSUMED,
                notes="Test assignment"
            )
        )
        return state

    def test_b0_fixed_pass_ordering(self):
        c1 = self._create_candidate("c1", 0.5, 0.9, ImportanceTier.LOW)
        c2 = self._create_candidate("c2", 0.9, 0.2, ImportanceTier.HIGH)
        c3 = self._create_candidate("c3", 0.7, 0.5, ImportanceTier.MEDIUM)
        
        policy = B0FixedPassPolicy()
        ranked = policy.rank_candidates([c1, c2, c3])
        # Preserves sequential input order
        self.assertEqual([c.detection.candidate_id for c in ranked], ["c1", "c2", "c3"])
        
        # Benefit = weight * confidence
        # c2 benefit = 4.0 * 0.9 = 3.6
        self.assertEqual(policy.evaluate_benefit(c2), 3.6)

    def test_b1_uncertainty_first_ordering(self):
        c1 = self._create_candidate("c1", 0.9, 0.2, ImportanceTier.HIGH)
        c2 = self._create_candidate("c2", 0.5, 0.9, ImportanceTier.LOW)
        c3 = self._create_candidate("c3", 0.7, 0.6, ImportanceTier.MEDIUM)
        
        policy = B1UncertaintyFirstPolicy()
        ranked = policy.rank_candidates([c1, c2, c3])
        # Sorted descending by uncertainty: c2 (0.9), c3 (0.6), c1 (0.2)
        self.assertEqual([c.detection.candidate_id for c in ranked], ["c2", "c3", "c1"])
        
        # Benefit = weight * uncertainty
        # c3 benefit = 2.0 * 0.6 = 1.2
        self.assertEqual(policy.evaluate_benefit(c3), 1.2)

    def test_policy_registry(self):
        self.assertIn("B0", POLICY_CATALOG)
        self.assertIn("B1", POLICY_CATALOG)
        self.assertIn("B2", POLICY_CATALOG)
        self.assertIn("B3", POLICY_CATALOG)
        self.assertIn("B4", POLICY_CATALOG)
        self.assertIn("P1", POLICY_CATALOG)
        self.assertIn("P2", POLICY_CATALOG)
        self.assertIn("P5", POLICY_CATALOG)

        self.assertEqual(POLICY_CATALOG["B0"].status, PolicyStatus.IMPLEMENTED)
        self.assertEqual(POLICY_CATALOG["B1"].status, PolicyStatus.IMPLEMENTED)
        self.assertEqual(POLICY_CATALOG["B2"].status, PolicyStatus.IMPLEMENTED)
        self.assertEqual(POLICY_CATALOG["B3"].status, PolicyStatus.IMPLEMENTED)
        self.assertEqual(POLICY_CATALOG["B4"].status, PolicyStatus.PLANNED)
        self.assertEqual(POLICY_CATALOG["P1"].status, PolicyStatus.SUPPLEMENTARY_BASELINE)

        # Factory returns instances of implemented policies
        p0 = get_policy("B0")
        self.assertIsInstance(p0, B0FixedPassPolicy)
        p1 = get_policy("B1")
        self.assertIsInstance(p1, B1UncertaintyFirstPolicy)
        p2 = get_policy("B2")
        self.assertIsInstance(p2, B2AdaptiveComputationPolicy)
        p3 = get_policy("B3")
        self.assertIsInstance(p3, B3JointPolicy)

        # Planned policy raises NotImplementedError with clear description
        with self.assertRaises(NotImplementedError):
            get_policy("B4")


if __name__ == "__main__":
    unittest.main()
