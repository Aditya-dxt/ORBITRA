"""Unit tests for Sub-Meter High-Resolution Scene Loader and Verification Engine."""

import os
import shutil
import tempfile
import unittest
import numpy as np

from SatQuery.satquery.data.submeter_highres_loader import (
    SUBMETER_HOTSPOTS,
    SubmeterHighresSceneLoader,
    deg2tile,
    tile2deg,
)
from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer


class TestSubmeterScenes(unittest.TestCase):
    """Test suite for sub-meter high-resolution scenes."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_satquery_submeter_")
        self.data_dir = os.path.join(self.test_dir, "data")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        self.loader = SubmeterHighresSceneLoader(
            repo_root=self.test_dir,
            data_dir=self.data_dir,
            exports_dir=self.exports_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_submeter_hotspots_metadata(self):
        """Verify all 5 strategic sub-meter hotspots have strictly valid metadata."""
        expected_keys = [
            "kanpur_bhauti_psit",
            "kanpur_panki_logistics",
            "delhi_cybercity_expressway",
            "bengaluru_electronic_city_metro",
            "chennai_sriperumbudur_industrial",
        ]
        for key in expected_keys:
            self.assertIn(key, SUBMETER_HOTSPOTS)
            info = SUBMETER_HOTSPOTS[key]
            self.assertTrue(len(info["name"]) > 5)
            self.assertTrue(len(info["description"]) > 10)
            self.assertEqual(info["zoom"], 18)
            self.assertAlmostEqual(info["gsd_m_per_px"], 0.59, places=2)
            self.assertIn("pre_release", info)
            self.assertIn("post_release", info)
            self.assertIn("pre_date", info)
            self.assertIn("post_date", info)
            self.assertTrue(8.0 <= info["home_lat"] <= 36.0)
            self.assertTrue(68.0 <= info["home_lon"] <= 97.0)

    def test_deg2tile_and_tile2deg_roundtrip(self):
        """Verify Web Mercator tile conversion is mathematically sound and invertible."""
        lat, lon = 26.4475, 80.1975
        zoom = 18
        tx, ty = deg2tile(lat, lon, zoom)
        self.assertIsInstance(tx, int)
        self.assertIsInstance(ty, int)
        self.assertGreater(tx, 0)
        self.assertGreater(ty, 0)

        # Recover bounding box NW corner
        recovered_lat, recovered_lon = tile2deg(tx, ty, zoom)
        # Should be within 1 tile width (~0.0014 degrees at zoom 18)
        self.assertAlmostEqual(recovered_lat, lat, delta=0.003)
        self.assertAlmostEqual(recovered_lon, lon, delta=0.003)

    def test_submeter_chip_extraction(self):
        """Verify that _extract_zoom_chip produces a sharp 4-panel image without error."""
        img_pre = np.full((300, 300, 3), 110, dtype=np.uint8)
        img_post = np.full((300, 300, 3), 190, dtype=np.uint8)

        # Place synthetic building change
        img_post[60:120, 60:120] = [255, 30, 30]

        bbox = [60, 60, 120, 120]
        chip = self.loader._extract_zoom_chip(img_pre, img_post, bbox, padding=15, height=140)

        self.assertIsInstance(chip, np.ndarray)
        self.assertEqual(chip.ndim, 3)
        self.assertEqual(chip.shape[0], 140)
        self.assertEqual(chip.shape[2], 3)
        self.assertGreater(chip.shape[1], 140 * 3)

    def test_georeferencing_submeter_grid(self):
        """Verify local grid metric transformation for a sub-meter scene."""
        info = SUBMETER_HOTSPOTS["kanpur_bhauti_psit"]
        gsd = info["gsd_m_per_px"]  # 0.59 m/px
        geo = MissionGeoreferencer(
            home_lat=info["home_lat"],
            home_lon=info["home_lon"],
            home_alt=120.0,
            tile_anchor_x=0.0,
            tile_anchor_y=0.0,
            gsd_x=gsd,
            gsd_y=gsd,
            default_flight_alt=60.0,
        )

        # Center pixel (384, 384) in a 768x768 scene
        cx_m, cy_m, cz_m = geo.pixel_to_local_grid(384, 384)
        self.assertAlmostEqual(cx_m, 384 * gsd, places=2)
        self.assertAlmostEqual(cy_m, 384 * gsd, places=2)

    def test_report_generation_submeter(self):
        """Verify markdown report generation for sub-meter summaries."""
        mock_summaries = [
            {
                "hotspot_key": "kanpur_bhauti_psit",
                "name": "Kanpur / Bhauti PSIT Campus",
                "description": "Corridor test",
                "dates": {"t1": "2020-12-16", "t2": "2024-12-12"},
                "resolution": "0.59 m/pixel (Sub-meter Ultra-HD)",
                "subpixel_shift": {"dx_px": 0.2, "dy_px": -0.1},
                "total_candidates_detected": 12,
                "total_change_footprint_m2": 8500.0,
                "total_change_footprint_ha": 0.85,
                "top_inspections": [
                    {
                        "rank": 1,
                        "candidate_id": "cand_sq_sub_001",
                        "chip_file": "chip_1_test.png",
                        "area_m2": 2500.0,
                        "confidence": 0.98,
                        "uncertainty": 0.05,
                        "local_grid": {"x_meters": 50.0, "y_meters": 100.0, "z_meters": 60.0},
                        "bbox": [100, 100, 150, 150],
                    }
                ],
                "files": {
                    "ultra_hd_montage": "kanpur_montage.png",
                    "annotated_changes": "kanpur_annot.png",
                    "change_heatmap": "kanpur_heat.png",
                    "candidates_json": "kanpur_cands.json",
                },
            }
        ]

        md_path = self.loader.generate_comprehensive_report(mock_summaries)
        self.assertTrue(os.path.exists(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("kanpur_bhauti_psit", content)
        self.assertIn("0.59 m/pixel", content)
        self.assertIn("cand_sq_sub_001", content)
        self.assertIn("Ultra-HD 4-Panel Montage", content)


if __name__ == "__main__":
    unittest.main()
