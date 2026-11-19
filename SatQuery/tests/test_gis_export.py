"""Unit tests for the SatQuery GIS and GeoTIFF Exporter."""

import json
import os
import shutil
import unittest
import numpy as np
from PIL import Image

from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer
from SatQuery.satquery.vision.gis_export import GISExporter


class TestGISExport(unittest.TestCase):
    """Verifies GeoTIFF tag construction, GeoJSON topology, and mission pack generation."""

    def setUp(self):
        self.test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tmp_gis_test"))
        os.makedirs(self.test_dir, exist_ok=True)
        self.exporter = GISExporter(output_root=self.test_dir)
        self.geo = MissionGeoreferencer(
            home_lat=26.447000,
            home_lon=80.198000,
            home_alt=120.0,
            tile_anchor_x=0.0,
            tile_anchor_y=0.0,
            gsd_x=10.0,
            gsd_y=10.0,
            default_flight_alt=60.0,
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_geotiff_export_and_tag_integrity(self):
        """Verifies that exported GeoTIFF contains valid OGC PixelScale, Tiepoint, and GeoKey tags."""
        # 2D continuous array (heatmap)
        arr_2d = np.random.rand(64, 64).astype(np.float32)
        out_tif_2d = os.path.join(self.test_dir, "test_heatmap.tif")
        self.exporter.export_geotiff(arr_2d, out_tif_2d, self.geo)

        self.assertTrue(os.path.exists(out_tif_2d))
        with Image.open(out_tif_2d) as im:
            self.assertEqual(im.size, (64, 64))
            # ModelPixelScaleTag (33550)
            self.assertIn(33550, im.tag_v2)
            scale = im.tag_v2[33550]
            self.assertEqual(len(scale), 3)
            self.assertGreater(scale[0], 0.0)
            self.assertGreater(scale[1], 0.0)

            # ModelTiepointTag (33922)
            self.assertIn(33922, im.tag_v2)
            tie = im.tag_v2[33922]
            self.assertEqual(len(tie), 6)
            self.assertEqual(tie[0], 0.0)
            self.assertEqual(tie[1], 0.0)
            self.assertAlmostEqual(tie[3], 80.198, places=3)
            self.assertAlmostEqual(tie[4], 26.447, places=3)

            # GeoKeyDirectoryTag (34735)
            self.assertIn(34735, im.tag_v2)
            geokeys = im.tag_v2[34735]
            self.assertIn(4326, geokeys)

    def test_geojson_export_and_rfc7946_compliance(self):
        """Verifies RFC 7946 GeoJSON structure and polygon ring closure."""
        candidates = [
            {
                "candidate_id": "cand_test_001",
                "confidence": 0.55,
                "uncertainty": 0.98,
                "region": {
                    "bbox_pixels": [10, 20, 30, 40],
                    "local_grid": {"x_meters": 200.0, "y_meters": 300.0, "z_meters": 50.0},
                },
                "timestamp": "2023-12-01T00:00:00Z",
                "image_pair_id": "pair_test_01",
            }
        ]

        out_geojson = os.path.join(self.test_dir, "test_candidates.geojson")
        self.exporter.export_geojson(candidates, out_geojson, self.geo, zone_name="Test Zone")

        self.assertTrue(os.path.exists(out_geojson))
        with open(out_geojson, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 1)

        feat = data["features"][0]
        self.assertEqual(feat["type"], "Feature")
        self.assertEqual(feat["id"], "cand_test_001")
        self.assertEqual(feat["geometry"]["type"], "Polygon")

        # Closed linear ring: first point must equal last point
        ring = feat["geometry"]["coordinates"][0]
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring[0], ring[-1])

        # Properties validation
        props = feat["properties"]
        self.assertEqual(props["candidate_id"], "cand_test_001")
        self.assertEqual(props["confidence"], 0.55)
        self.assertEqual(props["pixel_area"], 400)
        self.assertIn("transit_distance_m", props)

    def test_export_mission_gis_pack(self):
        """Verifies full GIS pack generation for Kanpur mission corridor."""
        pack = self.exporter.export_mission_gis_pack("kanpur_bhauti")
        for key in [
            "pre_t1_geotiff",
            "post_t2_geotiff",
            "change_heatmap_geotiff",
            "binary_mask_geotiff",
            "candidates_geojson",
            "manifest_json",
        ]:
            self.assertTrue(os.path.exists(pack[key]), f"Missing expected GIS artifact: {key}")

        # Check manifest
        with open(pack["manifest_json"], "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["zone_key"], "kanpur_bhauti")
        self.assertEqual(manifest["crs"], "EPSG:4326 (WGS 84)")
        self.assertIn("affine_transform", manifest)


if __name__ == "__main__":
    unittest.main()
