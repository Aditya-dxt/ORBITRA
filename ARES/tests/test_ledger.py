"""Unit tests for the decision ledger and audit trail."""

import unittest

from ares.ledger.decision_ledger import DecisionLedger
from ares.schemas.candidate_state import ActionType
from ares.schemas.provenance import DataProvenance


class TestLedger(unittest.TestCase):
    """Verifies decision ledger logging, Joules and Wh units, and simulated outcome labels."""

    def test_record_decision_and_wh_conversion(self):
        ledger = DecisionLedger()
        rec = ledger.record_decision(
            candidate_id="cand_test_01",
            policy_id="B0",
            selected_action=ActionType.RECAPTURE,
            action_energy_joules=7200.0,
            battery_before_joules=20_000.0,
            battery_after_joules=12_800.0,
            required_reserve_joules=5000.0,
            reserve_feasible=True,
            estimated_benefit=3.4,
            reason="High priority candidate feasible",
            simulated_outcome="Target inspected"
        )
        self.assertEqual(rec.action_energy_joules, 7200.0)
        self.assertEqual(rec.action_energy_wh, 2.0)
        self.assertTrue(rec.simulated_outcome.startswith("[SIMULATED]"))
        self.assertEqual(rec.provenance, DataProvenance.SIMULATED)
        self.assertEqual(len(ledger.records), 1)

    def test_ledger_energy_aggregation(self):
        ledger = DecisionLedger()
        ledger.record_decision(
            candidate_id="cand_1",
            policy_id="B0",
            selected_action=ActionType.RECAPTURE,
            action_energy_joules=3000.0,
            battery_before_joules=10_000.0,
            battery_after_joules=7000.0,
            required_reserve_joules=2000.0,
            reserve_feasible=True,
            estimated_benefit=1.0,
            reason="Feasible",
            simulated_outcome="[SIMULATED] OK"
        )
        ledger.record_decision(
            candidate_id="cand_2",
            policy_id="B0",
            selected_action=ActionType.RETURN_HOME,
            action_energy_joules=0.0,
            battery_before_joules=7000.0,
            battery_after_joules=7000.0,
            required_reserve_joules=2000.0,
            reserve_feasible=False,
            estimated_benefit=0.0,
            reason="Infeasible reserve",
            simulated_outcome="[SIMULATED] Aborted"
        )
        self.assertEqual(ledger.total_energy_spent_joules(), 3000.0)
        counts = ledger.count_by_action()
        self.assertEqual(counts[ActionType.RECAPTURE.value], 1)
        self.assertEqual(counts[ActionType.RETURN_HOME.value], 1)


if __name__ == "__main__":
    unittest.main()
