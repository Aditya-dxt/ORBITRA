"""Unit tests for the SatQuery Mission Operations Dashboard Generator."""

import os
import unittest

from SatQuery.satquery.data.dashboard_generator import MissionDashboardGenerator


class TestDashboardGenerator(unittest.TestCase):
    """Verifies dashboard data bundling and HTML generation."""

    @classmethod
    def setUpClass(cls):
        cls.generator = MissionDashboardGenerator()
        cls.data_bundle = cls.generator.build_dashboard_data()

    def test_all_four_corridors_bundled(self):
        """Verifies that Kanpur, Delhi, Bengaluru, and Chennai are bundled with candidates."""
        zones = self.data_bundle["zones"]
        self.assertEqual(len(zones), 4)
        for key in ["kanpur_bhauti", "delhi_ncr", "bengaluru_tech", "chennai_sriperumbudur"]:
            self.assertIn(key, zones)
            z = zones[key]
            self.assertGreater(z["total_candidates"], 0)
            self.assertIn("pre_img_url", z)
            self.assertIn("post_img_url", z)
            self.assertIn("heatmap_url", z)

    def test_candidate_properties_and_ares_recommendation(self):
        """Verifies that candidate records contain telemetry and triage decisions."""
        kanpur = self.data_bundle["zones"]["kanpur_bhauti"]
        first_cand = kanpur["candidates"][0]
        self.assertIn("candidate_id", first_cand)
        self.assertIn("confidence", first_cand)
        self.assertIn("uncertainty", first_cand)
        self.assertIn("local_grid", first_cand)
        self.assertIn("ares_recommendation", first_cand)
        self.assertIn("ares_cost", first_cand)

    def test_html_compilation(self):
        """Verifies that generate_html writes an HTML file with embedded data."""
        out_html = self.generator.generate_html()
        self.assertTrue(os.path.exists(out_html))
        with open(out_html, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.startswith("<!DOCTYPE html>"))
        self.assertIn("ORBITRA MISSION CONTROL", content)
        self.assertIn("kanpur_bhauti", content)
        self.assertIn("swipe-range", content)


if __name__ == "__main__":
    unittest.main()
