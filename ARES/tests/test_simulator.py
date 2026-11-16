"""Unit tests for the discrete-event mission simulator."""

import unittest

from ares.policies.b0_fixed_pass import B0FixedPassPolicy
from ares.policies.b1_uncertainty_first import B1UncertaintyFirstPolicy
from ares.schemas.candidate_state import CandidateStatus
from ares.schemas.provenance import DataProvenance
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator
from ares.simulation.synthetic_data import create_synthetic_candidate_states


class TestSimulator(unittest.TestCase):
    """Verifies simulator execution under B0 and B1, reserve guardrails, and provenance tagging."""

    def test_simulator_run_b0_success(self):
        candidates = create_synthetic_candidate_states()
        sim = MissionSimulator(config=MissionSimulationConfig(initial_battery_joules=60_000.0))
        report = sim.run_mission(B0FixedPassPolicy(), candidates)

        self.assertEqual(report.policy_id, "B0")
        self.assertEqual(report.provenance, DataProvenance.SIMULATED)
        self.assertTrue(report.safe_return_completed)
        self.assertGreater(report.candidates_inspected, 0)
        self.assertGreater(report.final_battery_joules, 0.0)
        self.assertGreaterEqual(len(sim.ledger.records), report.candidates_inspected + 1)

    def test_simulator_run_b1_uncertainty_order(self):
        candidates = create_synthetic_candidate_states()
        sim = MissionSimulator(config=MissionSimulationConfig(initial_battery_joules=60_000.0))
        report = sim.run_mission(B1UncertaintyFirstPolicy(), candidates)

        self.assertEqual(report.policy_id, "B1")
        self.assertTrue(report.safe_return_completed)
        
        # Verify first inspected candidate in B1 was the highest uncertainty one
        # Candidate 005 has uncertainty 0.91
        inspected_records = [
            r for r in sim.ledger.records
            if r.candidate_id != "MISSION_RETURN" and r.reserve_feasible
        ]
        self.assertEqual(inspected_records[0].candidate_id, "cand_synth_005")

    def test_return_reserve_triggers_early_abort_when_energy_constrained(self):
        candidates = create_synthetic_candidate_states()
        # Constrained battery budget: 15,000 J (drone can only do 1-2 inspections before needing to reserve return)
        sim = MissionSimulator(config=MissionSimulationConfig(initial_battery_joules=15_000.0))
        report = sim.run_mission(B0FixedPassPolicy(), candidates)

        self.assertTrue(report.safe_return_completed)
        self.assertGreater(report.candidates_deferred, 0)
        self.assertGreater(report.final_battery_joules, 0.0)

        # Check that deferred decisions are recorded in the ledger
        deferred_records = [r for r in sim.ledger.records if not r.reserve_feasible]
        self.assertGreater(len(deferred_records), 0)
        self.assertIn("return reserve", deferred_records[0].reason.lower())


if __name__ == "__main__":
    unittest.main()
