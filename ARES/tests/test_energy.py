"""Unit tests for energy model, kinematic calculations, and unit conversions."""

import unittest

from ares.energy.model import (
    DroneEnergyModel,
    DroneEnergyParameters,
    euclidean_distance,
)
from ares.energy.units import (
    format_energy_display,
    joules_to_wh,
    wh_to_joules,
)
from ares.schemas.provenance import DataProvenance
from ares.schemas.satquery_record import LocalGridCoordinates


class TestEnergy(unittest.TestCase):
    """Verifies energy calculations, units in Joules, display Wh, and assumptions."""

    def test_joules_to_wh_conversion(self):
        self.assertEqual(joules_to_wh(3600.0), 1.0)
        self.assertEqual(joules_to_wh(7200.0), 2.0)
        self.assertEqual(wh_to_joules(1.0), 3600.0)
        self.assertEqual(wh_to_joules(2.5), 9000.0)
        with self.assertRaises(ValueError):
            joules_to_wh(-100.0)
        with self.assertRaises(ValueError):
            wh_to_joules(-1.0)

    def test_format_energy_display(self):
        s = format_energy_display(7200.0)
        self.assertIn("7,200.0 J", s)
        self.assertIn("2.00 Wh", s)

    def test_euclidean_distance(self):
        p1 = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        p2 = LocalGridCoordinates(x_meters=300.0, y_meters=400.0, z_meters=0.0)
        self.assertAlmostEqual(euclidean_distance(p1, p2), 500.0)

    def test_starting_assumptions_provenance(self):
        params = DroneEnergyParameters()
        self.assertEqual(params.k_drag_exponent.value, 2.0)
        self.assertEqual(params.k_drag_exponent.provenance, DataProvenance.ASSUMED)
        self.assertEqual(params.flight_power_watts.provenance, DataProvenance.ASSUMED)

    def test_transit_energy_calculation(self):
        model = DroneEnergyModel()
        # Distance: 120m at 12m/s = 10s. Power: 180W -> Energy = 1800 Joules
        p1 = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        p2 = LocalGridCoordinates(x_meters=120.0, y_meters=0.0, z_meters=0.0)
        energy_j = model.transit_energy_joules(p1, p2)
        self.assertAlmostEqual(energy_j, 1800.0)

    def test_estimate_recapture_action_energy(self):
        model = DroneEnergyModel()
        p1 = LocalGridCoordinates(x_meters=0.0, y_meters=0.0, z_meters=0.0)
        p2 = LocalGridCoordinates(x_meters=120.0, y_meters=0.0, z_meters=0.0)
        # e_transit = 1800 J
        # e_hover (10s * 220W) = 2200 J
        # e_capture = 450 J
        # e_compute = 350 J
        # e_comms = 120 J
        # Total = 1800 + 2200 + 450 + 350 + 120 = 4920 J
        action_j = model.estimate_recapture_action_energy(p1, p2, hover_sec=10.0)
        self.assertAlmostEqual(action_j, 4920.0)


if __name__ == "__main__":
    unittest.main()
