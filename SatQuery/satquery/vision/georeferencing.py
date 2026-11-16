"""Georeferencing and spatial coordinate transformation for SatQuery.

Translates between:
1. Image pixel coordinates (u, v) and bounding boxes [xmin, ymin, xmax, ymax]
2. Local ENU metric grid [x_meters, y_meters, z_meters] relative to home base [0, 0, 0]
3. Geodetic coordinates (latitude, longitude, altitude) on WGS-84 ellipsoid

Assumptions (agreed with ARES module lead):
- Tile Anchor: (X_tile, Y_tile) is the local metric coordinate of image pixel (0, 0).
- Image Axes Alignment: Pixel column (u) increases Eastward (+x), pixel row (v) corresponds to
  top-down imagery where local Northing (y) = Y_tile + (v * GSD_y) or top-left offset.
- Ground Sampling Distance (GSD): Uniform 0.5 m/pixel (GSD_x = GSD_y = 0.5).
- Geodetic Conversion: Labeled explicitly as a local flat-Earth / ellipsoidal approximation
  around the mission home base (WGS-84 reference).
"""

import math
from typing import Dict, List, Optional, Tuple


class MissionGeoreferencer:
    """Handles spatial coordinate transformations for an aerial/satellite mission scene."""

    # Standard WGS-84 reference ellipsoid parameters
    WGS84_A = 6378137.0          # Semi-major axis (meters)
    WGS84_F = 1.0 / 298.257223563 # Flattening
    WGS84_B = WGS84_A * (1.0 - WGS84_F)
    WGS84_E2 = (WGS84_A**2 - WGS84_B**2) / (WGS84_A**2)

    def __init__(
        self,
        home_lat: float = 39.900000,
        home_lon: float = 116.400000,
        home_alt: float = 0.0,
        tile_anchor_x: float = 160.5,
        tile_anchor_y: float = 217.0,
        gsd_x: float = 0.5,
        gsd_y: float = 0.5,
        default_flight_alt: float = 50.0,
    ):
        """
        Initialize the georeferencer.
        
        Args:
            home_lat: Latitude of mission home base [0, 0, 0] in decimal degrees.
            home_lon: Longitude of mission home base [0, 0, 0] in decimal degrees.
            home_alt: Altitude of mission home base in meters above sea level.
            tile_anchor_x: Local Easting (meters) of the scene image pixel (0, 0).
            tile_anchor_y: Local Northing (meters) of the scene image pixel (0, 0).
            gsd_x: Ground Sampling Distance along X axis in meters/pixel.
            gsd_y: Ground Sampling Distance along Y axis in meters/pixel.
            default_flight_alt: Default drone flight altitude Above Ground Level (AGL) in meters.
        """
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt = home_alt
        self.tile_anchor_x = tile_anchor_x
        self.tile_anchor_y = tile_anchor_y
        self.gsd_x = gsd_x
        self.gsd_y = gsd_y
        self.default_flight_alt = default_flight_alt

        # Precompute meridional and parallel radii of curvature at home_lat
        lat_rad = math.radians(home_lat)
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        denom = math.sqrt(1.0 - self.WGS84_E2 * sin_lat**2)

        # Meridional radius (North-South sensitivity in meters per radian)
        self.m_radius = (self.WGS84_A * (1.0 - self.WGS84_E2)) / (denom**3)
        # Transverse prime vertical radius
        self.n_radius = self.WGS84_A / denom
        # Parallel radius (East-West sensitivity in meters per radian)
        self.p_radius = self.n_radius * cos_lat

        # Meters per degree
        self.meters_per_deg_lat = self.m_radius * (math.pi / 180.0)
        self.meters_per_deg_lon = self.p_radius * (math.pi / 180.0)

    def pixel_to_local_grid(self, u: float, v: float, z: Optional[float] = None) -> Tuple[float, float, float]:
        """Convert pixel coordinate (u, v) to local ENU meter coordinates [x, y, z].
        
        Assumption:
            x_meters = tile_anchor_x + u * gsd_x
            y_meters = tile_anchor_y + v * gsd_y
        """
        x_meters = self.tile_anchor_x + (u * self.gsd_x)
        y_meters = self.tile_anchor_y + (v * self.gsd_y)
        z_meters = z if z is not None else self.default_flight_alt
        return round(x_meters, 4), round(y_meters, 4), round(z_meters, 2)

    def bbox_to_local_grid(self, bbox_pixels: List[int], z: Optional[float] = None) -> Tuple[float, float, float]:
        """Compute local metric coordinate for the center of an image pixel bounding box [xmin, ymin, xmax, ymax]."""
        xmin, ymin, xmax, ymax = bbox_pixels
        u_center = (xmin + xmax) / 2.0
        v_center = (ymin + ymax) / 2.0
        return self.pixel_to_local_grid(u_center, v_center, z=z)

    def local_grid_to_geodetic(
        self, x_meters: float, y_meters: float, z_meters: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """Transform local ENU coordinates to WGS-84 geodetic coordinates.
        
        NOTE: This is documented as a local approximation valid for tactical UAV flight envelopes (< 15 km).
        """
        delta_lat = y_meters / self.meters_per_deg_lat
        delta_lon = x_meters / self.meters_per_deg_lon

        center_lat = self.home_lat + delta_lat
        center_lon = self.home_lon + delta_lon
        alt_m = (z_meters if z_meters is not None else self.default_flight_alt) + self.home_alt

        return round(center_lat, 6), round(center_lon, 6), round(alt_m, 2)

    def geodetic_to_local_grid(
        self, lat: float, lon: float, alt_m: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """Inverse transformation: geodetic coordinates back to local ENU meter coordinates."""
        delta_lat = lat - self.home_lat
        delta_lon = lon - self.home_lon

        y_meters = delta_lat * self.meters_per_deg_lat
        x_meters = delta_lon * self.meters_per_deg_lon
        z_meters = (alt_m - self.home_alt) if alt_m is not None else self.default_flight_alt

        return round(x_meters, 4), round(y_meters, 4), round(z_meters, 2)

    def local_grid_to_pixel(self, x_meters: float, y_meters: float) -> Tuple[float, float]:
        """Inverse transformation: local ENU meter coordinates back to pixel coordinates (u, v)."""
        u = (x_meters - self.tile_anchor_x) / self.gsd_x
        v = (y_meters - self.tile_anchor_y) / self.gsd_y
        return round(u, 2), round(v, 2)

    def create_region_geometry(
        self,
        bbox_pixels: List[int],
        flight_alt_m: Optional[float] = None
    ) -> Dict:
        """Helper to create an agreed RegionGeometry dictionary from a pixel bounding box."""
        x, y, z = self.bbox_to_local_grid(bbox_pixels, z=flight_alt_m)
        lat, lon, alt = self.local_grid_to_geodetic(x, y, z)

        return {
            "crs": "local_meter_grid",
            "local_grid": {
                "x_meters": x,
                "y_meters": y,
                "z_meters": z,
            },
            "coordinates": {
                "center_lat": lat,
                "center_lon": lon,
                "altitude_m": alt,
            },
            "bbox_pixels": bbox_pixels,
        }
