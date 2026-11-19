"""Unit tests for the Multi-Zone Indian Satellite Mission Gallery Generator."""

import os
import unittest
import numpy as np

from SatQuery.satquery.data.mission_gallery import (
    MissionGalleryGenerator,
    compute_shannon_entropy,
)


class TestMissionGallery(unittest.TestCase):
    """Verifies that the Indian Mission Gallery builds, validates, and exports properly."""

    @classmethod
    def setUpClass(cls):
        cls.generator = MissionGalleryGenerator()
        cls.gallery_data = cls.generator.build_gallery(generate_chips=False)

    def test_all_four_indian_corridors_present(self):
        """Verifies that Kanpur, Delhi, Bengaluru, and Chennai corridors are all evaluated."""
        zones = self.gallery_data["mission_zones"]
        self.assertEqual(len(zones), 4)
        self.assertIn("kanpur_bhauti", zones)
        self.assertIn("delhi_ncr", zones)
        self.assertIn("bengaluru_tech", zones)
        self.assertIn("chennai_sriperumbudur", zones)

    def test_aggregate_candidate_count_and_entropy_bounds(self):
        """Verifies aggregate counts and that every candidate satisfies Shannon entropy constraints."""
        agg = self.gallery_data["aggregate_statistics"]
        self.assertEqual(agg["total_candidates"], 101)
        self.assertGreater(agg["total_change_area_hectares"], 100.0)
        self.assertGreater(agg["mean_confidence"], 0.0)
        self.assertLess(agg["mean_confidence"], 1.0)

        # Verify Shannon entropy constraint across top candidates
        for z_key, z in self.gallery_data["mission_zones"].items():
            for c in z.get("top_candidates", []):
                p = c["confidence"]
                u = c["uncertainty"]
                h_p = compute_shannon_entropy(p)
                self.assertLessEqual(abs(u - h_p), 0.15001, f"Candidate {c['candidate_id']} violated entropy bound")

    def test_svg_and_markdown_exports(self):
        """Verifies SVG overview and markdown documentation files are created and valid."""
        svg_path = self.generator.generate_gallery_svg(self.gallery_data)
        self.assertTrue(os.path.exists(svg_path))
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        self.assertTrue(svg_content.startswith("<svg"))
        self.assertIn("ORBITRA Multi-Zone Indian Satellite Mission Gallery", svg_content)
        self.assertIn("kanpur_bhauti", svg_content)

        md_path = self.generator.generate_gallery_markdown(self.gallery_data)
        self.assertTrue(os.path.exists(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        self.assertIn("Kanpur / Bhauti Corridor", md_content)
        self.assertIn("Delhi NCR / Gurugram Development Corridor", md_content)
        self.assertIn("Bengaluru Electronic City Infrastructure", md_content)
        self.assertIn("Chennai / Sriperumbudur Industrial Corridor", md_content)

    def test_inspection_chip_extraction(self):
        """Tests that candidate chip extraction produces 4-panel image with non-zero dimensions."""
        img_pre = np.zeros((200, 200, 3), dtype=np.uint8)
        img_post = np.ones((200, 200, 3), dtype=np.uint8) * 150
        bbox = [40, 40, 80, 80]

        chip = self.generator.extract_candidate_chip(img_pre, img_post, bbox, target_height=80)
        self.assertEqual(len(chip.shape), 3)
        self.assertEqual(chip.shape[0], 80)
        self.assertGreater(chip.shape[1], 80)
        self.assertEqual(chip.shape[2], 3)

    def test_shannon_entropy_function(self):
        """Tests mathematical properties of normalized binary Shannon entropy."""
        self.assertAlmostEqual(compute_shannon_entropy(0.5), 1.0, places=3)
        self.assertAlmostEqual(compute_shannon_entropy(0.0), 0.0, places=3)
        self.assertAlmostEqual(compute_shannon_entropy(1.0), 0.0, places=3)
        self.assertAlmostEqual(compute_shannon_entropy(0.2), compute_shannon_entropy(0.8), places=3)


if __name__ == "__main__":
    unittest.main()
