"""Unit tests for spatial georeferencing and coordinate transformation."""

import unittest
from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer


class TestGeoreferencing(unittest.TestCase):
    """Verifies pixel-to-metric, metric-to-geodetic, and inverse coordinate transformations."""

    def setUp(self):
        # Anchor configured exactly to reconciled sample parameters
        self.geo = MissionGeoreferencer(
            home_lat=39.900000,
            home_lon=116.400000,
            home_alt=0.0,
            tile_anchor_x=160.5,
            tile_anchor_y=217.0,
            gsd_x=0.5,
            gsd_y=0.5,
            default_flight_alt=50.0,
        )

    def test_tile_anchor_at_pixel_origin(self):
        """Pixel (0, 0) must exactly equal tile anchor local coordinates."""
        x, y, z = self.geo.pixel_to_local_grid(0, 0)
        self.assertEqual(x, 160.5)
        self.assertEqual(y, 217.0)
        self.assertEqual(z, 50.0)

    def test_reconciled_sample_bbox_transformation(self):
        """Bounding box [128, 160, 212, 244] must yield x=245.5, y=318.0, lat=39.902864, lon=116.402875."""
        bbox = [128, 160, 212, 244]
        # Centroid: u = 170, v = 202
        # x = 160.5 + 170 * 0.5 = 245.5
        # y = 217.0 + 202 * 0.5 = 318.0
        x, y, z = self.geo.bbox_to_local_grid(bbox)
        self.assertAlmostEqual(x, 245.5, places=3)
        self.assertAlmostEqual(y, 318.0, places=3)
        self.assertEqual(z, 50.0)

        lat, lon, alt = self.geo.local_grid_to_geodetic(x, y, z)
        self.assertAlmostEqual(lat, 39.902864, places=5)
        self.assertAlmostEqual(lon, 116.402875, places=5)
        self.assertEqual(alt, 50.0)

    def test_inverse_geodetic_to_local(self):
        """Geodetic back to local metric must recover original coordinates."""
        x_orig, y_orig, z_orig = 350.0, 420.0, 60.0
        lat, lon, alt = self.geo.local_grid_to_geodetic(x_orig, y_orig, z_orig)
        x_rec, y_rec, z_rec = self.geo.geodetic_to_local_grid(lat, lon, alt)

        self.assertAlmostEqual(x_orig, x_rec, places=1)
        self.assertAlmostEqual(y_orig, y_rec, places=1)
        self.assertAlmostEqual(z_orig, z_rec, places=1)

    def test_inverse_local_to_pixel(self):
        """Local grid back to pixel space must recover centroid."""
        u_orig, v_orig = 170.0, 202.0
        x, y, _ = self.geo.pixel_to_local_grid(u_orig, v_orig)
        u_rec, v_rec = self.geo.local_grid_to_pixel(x, y)

        self.assertAlmostEqual(u_orig, u_rec, places=2)
        self.assertAlmostEqual(v_orig, v_rec, places=2)


if __name__ == "__main__":
    unittest.main()
