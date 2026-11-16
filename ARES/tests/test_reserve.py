"""Unit tests for the return-reserve guardrail and safe return rules."""

import unittest

from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator, ReturnReserveConfig
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import LocalGridCoordinates


class TestReserve(unittest.TestCase):
    """Verifies return energy from post-action position, single uncertainty allowance, and wind margin."""

    def setUp(self):
        self.model = DroneEnergyModel()
        self.config = ReturnReserveConfig()
        self.calc = ReturnReserveCalculator(energy_model=self.model, config=self.config)
        self.home = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)

    def test_post_action_evaluation_and_margins(self):
        # Post-action target at (240m, 0m, 0m).
        # Transit time back to home = 240 / 12 = 20s.
        # Nominal return energy = 20s * 180W = 3600 J.
        # Reserve margin = 20% (0.20) -> 3600 * 1.20 = 4320 J.
        # Wind margin = 1200 J.
        # Total required reserve = 4320 + 1200 = 5520 J.
        target_pos = LocalGridCoordinates(x_meters=240.0, y_meters=0.0, z_meters=0.0)
        
        nominal = self.calc.calculate_nominal_return_energy_joules(target_pos, self.home)
        self.assertAlmostEqual(nominal, 3600.0)

        required = self.calc.calculate_required_reserve_joules(target_pos, self.home)
        self.assertAlmostEqual(required, 5520.0)

    def test_feasibility_check_success(self):
        target_pos = LocalGridCoordinates(x_meters=240.0, y_meters=0.0, z_meters=0.0)
        # Action cost = 4000 J. Required reserve = 5520 J.
        # Battery = 10,000 J.
        # Remaining after action = 10,000 - 4,000 = 6,000 J >= 5,520 J -> Feasible!
        result = self.calc.check_action_feasibility(
            current_battery_joules=10_000.0,
            estimated_action_joules=4_000.0,
            post_action_pos=target_pos,
            home_pos=self.home
        )
        self.assertTrue(result.is_feasible)
        self.assertEqual(result.remaining_after_action_joules, 6000.0)
        self.assertEqual(result.required_reserve_joules, 5520.0)

    def test_feasibility_check_violation_triggers_guardrail(self):
        target_pos = LocalGridCoordinates(x_meters=240.0, y_meters=0.0, z_meters=0.0)
        # Battery = 8,000 J. Action cost = 4000 J.
        # Remaining after action = 4,000 J < 5,520 J -> Infeasible!
        result = self.calc.check_action_feasibility(
            current_battery_joules=8_000.0,
            estimated_action_joules=4_000.0,
            post_action_pos=target_pos,
            home_pos=self.home
        )
        self.assertFalse(result.is_feasible)
        self.assertIn("violates required return reserve", result.reason)

    def test_provenance_of_reserve_parameters(self):
        self.assertEqual(self.config.reserve_uncertainty_margin.provenance, DataProvenance.ASSUMED)
        self.assertEqual(self.config.wind_margin_joules.provenance, DataProvenance.ASSUMED)


if __name__ == "__main__":
    unittest.main()
