"""Unit and integration tests for real Indian satellite data loading and mission processing."""

import os
import unittest

from SatQuery.satquery.data.india_satellite_data import (
    INDIAN_MISSION_ZONES,
    IndiaSatelliteDataLoader,
)
from SatQuery.satquery.pipeline import SatQueryPipeline
from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer


class TestIndiaSatelliteData(unittest.TestCase):
    """Verifies that real Indian satellite scenes are correctly loaded, georeferenced, and processed."""

    def setUp(self):
        self.loader = IndiaSatelliteDataLoader()

    def test_indian_mission_zones_metadata(self):
        """Checks predefined Indian zones (Kanpur, Delhi, Bengaluru, Chennai)."""
        self.assertIn("kanpur_bhauti", INDIAN_MISSION_ZONES)
        self.assertIn("bengaluru_tech", INDIAN_MISSION_ZONES)
        self.assertIn("delhi_ncr", INDIAN_MISSION_ZONES)
        self.assertIn("chennai_sriperumbudur", INDIAN_MISSION_ZONES)

        kanpur = INDIAN_MISSION_ZONES["kanpur_bhauti"]
        self.assertAlmostEqual(kanpur["home_lat"], 26.447, places=3)
        self.assertAlmostEqual(kanpur["home_lon"], 80.198, places=3)

    def test_load_cached_kanpur_scene(self):
        """Loads cached real Sentinel-2 Level-2A bitemporal pair for Kanpur."""
        scene = self.loader.get_indian_scene_pair("kanpur_bhauti")
        self.assertEqual(scene["zone_key"], "kanpur_bhauti")
        self.assertEqual(len(scene["img_pre"].shape), 3)
        self.assertEqual(len(scene["img_post"].shape), 3)
        self.assertEqual(scene["img_pre"].shape, scene["img_post"].shape)
        self.assertIn("pre_datetime", scene["metadata"])
        self.assertIn("post_datetime", scene["metadata"])

    def test_pipeline_on_real_indian_scene(self):
        """Runs change detection pipeline on real Kanpur satellite pair."""
        scene = self.loader.get_indian_scene_pair("kanpur_bhauti")
        geo = MissionGeoreferencer(
            home_lat=scene["home_lat"],
            home_lon=scene["home_lon"],
            home_alt=126.0,
            tile_anchor_x=0.0,
            tile_anchor_y=0.0,
            gsd_x=10.0,
            gsd_y=10.0,
            default_flight_alt=60.0,
        )
        pipeline = SatQueryPipeline(georeferencer=geo, threshold=0.30, min_pixel_area=15)
        results = pipeline.process_pair(
            img_pre=scene["img_pre"],
            img_post=scene["img_post"],
            image_pair_id="pair_test_kanpur",
            timestamp=scene["metadata"]["post_datetime"],
        )
        candidates = results["candidates"]
        self.assertGreater(len(candidates), 0)

        # Verify candidate geodetic coordinates fall within Kanpur region
        first = candidates[0]
        self.assertAlmostEqual(first.region.coordinates.center_lat, 26.48, delta=0.1)
        self.assertAlmostEqual(first.region.coordinates.center_lon, 80.20, delta=0.1)

    def test_image_pair_resolver_benchmark_and_real_scenes(self):
        """Verifies ImagePairResolver maps pair IDs to valid pre/post image arrays."""
        from SatQuery.satquery.data.image_resolver import ImagePairResolver

        resolver = ImagePairResolver()

        # 1. Benchmark pair resolution (synthetic)
        bench = resolver.resolve("pair_levir_test_042")
        self.assertTrue(bench.is_synthetic)
        self.assertEqual(bench.img_pre.shape, (256, 256, 3))
        self.assertEqual(bench.img_post.shape, (256, 256, 3))
        self.assertIn(bench.source_type, ["DISK_FILE_BENCHMARK", "DETERMINISTIC_SYNTHETIC"])

        # 2. Real Sentinel-2 pair resolution (if cached on disk)
        real = resolver.resolve("pair_sentinel2_kanpur_bhauti")
        if real.source_type == "DISK_FILE_REAL":
            self.assertFalse(real.is_synthetic)
            self.assertEqual(real.img_pre.shape, (512, 512, 3))
            self.assertIn("Kanpur", real.description)

        # 3. Unmapped fallback pair
        fallback = resolver.resolve("pair_unknown_id_xyz")
        self.assertTrue(fallback.is_synthetic)
        self.assertEqual(fallback.img_pre.shape, (256, 256, 3))


if __name__ == "__main__":
    unittest.main()
