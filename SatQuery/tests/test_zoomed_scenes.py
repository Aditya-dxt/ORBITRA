"""Unit tests for Zoomed Real Satellite Imagery Loader and Visual Verification."""

import os
import shutil
import tempfile
import unittest
import numpy as np

from SatQuery.satquery.data.zoomed_scene_loader import (
    ZOOMED_MISSION_HOTSPOTS,
    ZoomedSceneLoader,
)
from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer


class TestZoomedScenes(unittest.TestCase):
    """Test suite for zoomed real satellite scenes processing."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_satquery_zoomed_")
        self.data_dir = os.path.join(self.test_dir, "data")
        self.exports_dir = os.path.join(self.test_dir, "exports")
        self.loader = ZoomedSceneLoader(
            repo_root=self.test_dir,
            data_dir=self.data_dir,
            exports_dir=self.exports_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_zoomed_mission_hotspots_metadata(self):
        """Verify all 5 strategic hotspots have strictly valid geographic metadata."""
        expected_keys = [
            "kanpur_bhauti_nh19",
            "kanpur_panki_industrial",
            "delhi_gurugram_cybercity",
            "bengaluru_electronic_city",
            "chennai_sriperumbudur",
        ]
        for key in expected_keys:
            self.assertIn(key, ZOOMED_MISSION_HOTSPOTS)
            info = ZOOMED_MISSION_HOTSPOTS[key]
            self.assertTrue(len(info["name"]) > 5)
            self.assertTrue(len(info["description"]) > 10)
            self.assertIn("home_lat", info)
            self.assertIn("home_lon", info)
            self.assertTrue(8.0 <= info["home_lat"] <= 36.0)
            self.assertTrue(68.0 <= info["home_lon"] <= 97.0)

            # BBox format [min_lon, min_lat, max_lon, max_lat]
            bbox = info["bbox"]
            self.assertEqual(len(bbox), 4)
            self.assertLess(bbox[0], bbox[2])  # min_lon < max_lon
            self.assertLess(bbox[1], bbox[3])  # min_lat < max_lat
            self.assertGreater(info.get("gsd_m_per_px", 0), 0)

    def test_zoom_chip_extraction(self):
        """Verify that _extract_zoom_chip produces a 4-panel image without error."""
        img_pre = np.full((256, 256, 3), 100, dtype=np.uint8)
        img_post = np.full((256, 256, 3), 180, dtype=np.uint8)

        # Place a synthetic change block
        img_post[50:100, 50:100] = [255, 20, 20]

        bbox = [50, 50, 100, 100]
        chip = self.loader._extract_zoom_chip(img_pre, img_post, bbox, padding=10, height=120)

        self.assertIsInstance(chip, np.ndarray)
        self.assertEqual(chip.ndim, 3)
        self.assertEqual(chip.shape[0], 120)
        self.assertEqual(chip.shape[2], 3)
        self.assertGreater(chip.shape[1], 120 * 3)

    def test_georeferencing_for_zoomed_hotspot(self):
        """Verify local grid metric transformation for a zoomed hotspot."""
        info = ZOOMED_MISSION_HOTSPOTS["kanpur_bhauti_nh19"]
        gsd = info.get("gsd_m_per_px", 5.0)
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

        # Origin pixel (0, 0)
        x_m, y_m, z_m = geo.pixel_to_local_grid(0, 0)
        self.assertEqual(x_m, 0.0)
        self.assertEqual(y_m, 0.0)
        lat, lon, alt = geo.local_grid_to_geodetic(x_m, y_m)
        self.assertAlmostEqual(lat, info["home_lat"], places=5)
        self.assertAlmostEqual(lon, info["home_lon"], places=5)

        # Center pixel (256, 256) at 5m/px should be 1280m from anchor
        cx_m, cy_m, cz_m = geo.pixel_to_local_grid(256, 256)
        self.assertAlmostEqual(cx_m, 256 * gsd, places=2)
        self.assertAlmostEqual(cy_m, 256 * gsd, places=2)

    def test_report_generation(self):
        """Verify report generation compiles markdown with summary data."""
        mock_summaries = [
            {
                "hotspot_key": "kanpur_bhauti_nh19",
                "name": "Kanpur / Bhauti PSIT Corridor",
                "description": "Corridor test",
                "dates": {"t1": "2021-11-15", "t2": "2023-11-20"},
                "subpixel_shift": {"dx_px": 0.5, "dy_px": -0.2},
                "total_candidates_detected": 4,
                "total_change_footprint_m2": 25000.0,
                "total_change_footprint_ha": 2.5,
                "top_inspections": [
                    {
                        "rank": 1,
                        "candidate_id": "cand_test_001",
                        "chip_file": "chip_1_test.png",
                        "area_m2": 12000.0,
                        "confidence": 0.95,
                        "uncertainty": 0.12,
                        "local_grid": {"x_meters": 120.0, "y_meters": 240.0, "z_meters": 60.0},
                        "bbox": [20, 20, 60, 60],
                    }
                ],
                "files": {
                    "widescreen_montage": "kanpur_montage.png",
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

        self.assertIn("kanpur_bhauti_nh19", content)
        self.assertIn("cand_test_001", content)
        self.assertIn("2.5 ha", content)
        self.assertIn("Widescreen 4-Panel Comparison", content)


if __name__ == "__main__":
    unittest.main()
