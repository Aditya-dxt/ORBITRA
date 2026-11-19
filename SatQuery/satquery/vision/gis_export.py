"""Geospatial GIS Exporter for SatQuery.

Exports bi-temporal satellite imagery, change heatmaps, binary masks, and candidate
regions into standard, industry-interoperable GIS formats:
1. OGC GeoTIFF (.tif) with embedded WGS-84 (EPSG:4326) tags:
   - ModelPixelScaleTag (33550)
   - ModelTiepointTag (33922)
   - GeoKeyDirectoryTag (34735)
2. RFC 7946 GeoJSON (.geojson) FeatureCollections for vector polygons.
3. Standard GIS Manifest (.json) with affine transform matrices and QGIS styling metadata.
"""

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, TiffImagePlugin

from .georeferencing import MissionGeoreferencer
from ..data.india_satellite_data import INDIAN_MISSION_ZONES, IndiaSatelliteDataLoader
from ..schemas.candidate_record import SatQueryCandidateRecord


class GISExporter:
    """Exports SatQuery raster and vector products to standards-compliant GIS formats."""

    def __init__(self, output_root: Optional[str] = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.exports_dir = os.path.join(base_dir, "exports")
        if output_root is None:
            output_root = os.path.join(self.exports_dir, "gis")
        self.output_root = output_root
        os.makedirs(self.output_root, exist_ok=True)

    @staticmethod
    def _build_geotiff_tags(
        georeferencer: MissionGeoreferencer,
        img_width: int,
        img_height: int,
        epsg_code: int = 4326,
    ) -> TiffImagePlugin.ImageFileDirectory_v2:
        """Construct standard OGC GeoTIFF directory tags for EPSG:4326 (WGS-84)."""
        # Top-left pixel (0, 0) in metric grid and geodetic coordinates
        x0, y0, _ = georeferencer.pixel_to_local_grid(0, 0)
        top_left_lat, top_left_lon, _ = georeferencer.local_grid_to_geodetic(x0, y0)

        # Angular pixel scale in degrees per pixel
        scale_lon_deg = float(georeferencer.gsd_x / georeferencer.meters_per_deg_lon)
        scale_lat_deg = float(georeferencer.gsd_y / georeferencer.meters_per_deg_lat)

        info = TiffImagePlugin.ImageFileDirectory_v2()

        # Tag 33550 (0x830E): ModelPixelScaleTag (ScaleX, ScaleY, ScaleZ)
        info[33550] = (scale_lon_deg, scale_lat_deg, 0.0)

        # Tag 33922 (0x8482): ModelTiepointTag (I, J, K, X, Y, Z) -> Maps pixel (0, 0, 0) to (Lon, Lat, 0)
        info[33922] = (0.0, 0.0, 0.0, float(top_left_lon), float(top_left_lat), 0.0)

        # Tag 34735 (0x87AF): GeoKeyDirectoryTag
        # Header: [Version=1, Revision=1, MinorRevision=0, NumberOfKeys=3]
        # GTModelTypeGeoKey (1024): 2 = ModelTypeGeographic
        # GTRasterTypeGeoKey (1025): 1 = RasterPixelIsArea
        # GeographicTypeGeoKey (2048): 4326 = GCS_WGS_84
        geokeys = (
            1, 1, 0, 3,
            1024, 0, 1, 2,
            1025, 0, 1, 1,
            2048, 0, 1, int(epsg_code),
        )
        info[34735] = geokeys

        return info

    def export_geotiff(
        self,
        image_data: np.ndarray,
        output_path: str,
        georeferencer: MissionGeoreferencer,
        epsg_code: int = 4326,
    ) -> str:
        """Save a 2D or 3D numpy array as a georeferenced GeoTIFF.
        
        Args:
            image_data: 2D uint8/float32 (mask/heatmap) or 3D RGB uint8 array.
            output_path: Destination file path ending with .tif or .tiff.
            georeferencer: MissionGeoreferencer instance with valid GSD and anchor.
            epsg_code: Coordinate Reference System EPSG code (default: 4326).
            
        Returns:
            Absolute path to the created GeoTIFF file.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        h, w = image_data.shape[:2]

        tiff_info = self._build_geotiff_tags(georeferencer, w, h, epsg_code=epsg_code)

        if image_data.dtype in (np.float32, np.float64):
            # Scale continuous probabilities [0.0, 1.0] to uint8 [0, 255] for standard GIS display
            norm = np.clip(image_data * 255.0, 0.0, 255.0).astype(np.uint8)
            pil_img = Image.fromarray(norm)
        elif len(image_data.shape) == 3 and image_data.shape[2] == 3:
            pil_img = Image.fromarray(image_data.astype(np.uint8), mode="RGB")
        else:
            pil_img = Image.fromarray(image_data.astype(np.uint8), mode="L")

        pil_img.save(output_path, format="TIFF", tiffinfo=tiff_info)
        return output_path

    def export_geojson(
        self,
        candidates: List[Union[Dict, SatQueryCandidateRecord]],
        output_path: str,
        georeferencer: MissionGeoreferencer,
        zone_name: str = "",
    ) -> str:
        """Export candidate change regions as a standard RFC 7946 GeoJSON FeatureCollection.
        
        Each candidate bounding box [xmin, ymin, xmax, ymax] is projected into a closed
        geodetic polygon [[lon, lat], ...] with detailed properties.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        features = []
        for c in candidates:
            if isinstance(c, SatQueryCandidateRecord):
                c_dict = c.model_dump()
            else:
                c_dict = c

            cand_id = c_dict.get("candidate_id", "cand_unknown")
            conf = float(c_dict.get("confidence", 0.0))
            unc = float(c_dict.get("uncertainty", 0.0))
            reg = c_dict.get("region", {})
            bbox = reg.get("bbox_pixels", [0, 0, 0, 0])
            local_grid = reg.get("local_grid", {})

            xmin, ymin, xmax, ymax = bbox

            # Calculate the 4 corners in geodetic coordinates:
            # Corner 1: (xmin, ymin)
            # Corner 2: (xmax, ymin)
            # Corner 3: (xmax, ymax)
            # Corner 4: (xmin, ymax)
            pixel_corners = [
                (xmin, ymin),
                (xmax, ymin),
                (xmax, ymax),
                (xmin, ymax),
                (xmin, ymin),  # Closed ring
            ]

            geodetic_ring = []
            for pu, pv in pixel_corners:
                xm, ym, zm = georeferencer.pixel_to_local_grid(pu, pv)
                glat, glon, _ = georeferencer.local_grid_to_geodetic(xm, ym, zm)
                # RFC 7946 GeoJSON format: [longitude, latitude]
                geodetic_ring.append([glon, glat])

            px_area = (xmax - xmin) * (ymax - ymin)
            area_m2 = px_area * (georeferencer.gsd_x * georeferencer.gsd_y)

            # Shannon entropy reference
            p_c = max(1e-6, min(1.0 - 1e-6, conf))
            h_p = - (p_c * math.log2(p_c) + (1.0 - p_c) * math.log2(1.0 - p_c))

            dist_m = math.sqrt(local_grid.get("x_meters", 0.0)**2 + local_grid.get("y_meters", 0.0)**2)

            feature = {
                "type": "Feature",
                "id": cand_id,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [geodetic_ring],
                },
                "properties": {
                    "candidate_id": cand_id,
                    "zone_name": zone_name,
                    "confidence": round(conf, 4),
                    "uncertainty": round(unc, 4),
                    "shannon_entropy_h_p": round(h_p, 4),
                    "pixel_area": int(px_area),
                    "area_m2": round(area_m2, 1),
                    "area_hectares": round(area_m2 / 10000.0, 3),
                    "bbox_pixels": bbox,
                    "local_grid_x_m": round(float(local_grid.get("x_meters", 0.0)), 1),
                    "local_grid_y_m": round(float(local_grid.get("y_meters", 0.0)), 1),
                    "local_grid_z_m": round(float(local_grid.get("z_meters", 50.0)), 1),
                    "transit_distance_m": round(dist_m, 1),
                    "timestamp": c_dict.get("timestamp", "N/A"),
                    "image_pair_id": c_dict.get("image_pair_id", "N/A"),
                },
            }
            features.append(feature)

        geojson_data = {
            "type": "FeatureCollection",
            "name": f"ORBITRA_{zone_name}_Candidates",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "features": features,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, indent=2)

        return output_path

    def export_mission_gis_pack(
        self,
        zone_key: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate and export a complete GIS distribution pack for a mission corridor."""
        if zone_key not in INDIAN_MISSION_ZONES:
            raise ValueError(f"Unknown zone '{zone_key}'. Available: {list(INDIAN_MISSION_ZONES.keys())}")

        zone_info = INDIAN_MISSION_ZONES[zone_key]
        target_dir = output_dir or os.path.join(self.output_root, zone_key)
        os.makedirs(target_dir, exist_ok=True)

        # 1. Load satellite pair and metadata
        loader = IndiaSatelliteDataLoader()
        scene_data = loader.get_indian_scene_pair(zone_key)
        img_pre = scene_data["img_pre"]
        img_post = scene_data["img_post"]
        meta = scene_data["metadata"]

        # 2. Configure Georeferencer
        geo = MissionGeoreferencer(
            home_lat=zone_info["home_lat"],
            home_lon=zone_info["home_lon"],
            home_alt=120.0,
            tile_anchor_x=0.0,
            tile_anchor_y=0.0,
            gsd_x=10.0,
            gsd_y=10.0,
            default_flight_alt=60.0,
        )

        # 3. Load or compute candidate records and change heatmaps
        candidates_json = os.path.join(self.exports_dir, f"candidates_{zone_key}.json")
        if not os.path.exists(candidates_json):
            from ..pipeline import SatQueryPipeline
            pipe = SatQueryPipeline(georeferencer=geo, threshold=0.35, min_pixel_area=15)
            res = pipe.process_pair(
                img_pre=img_pre,
                img_post=img_post,
                image_pair_id=f"pair_sentinel2_{zone_key}",
                timestamp=meta.get("post_datetime", "2023-12-01T00:00:00Z"),
            )
            pipe.export_candidates_to_json(res["candidates"], candidates_json)
            heatmap = res["heatmap"]
            mask = res["binary_mask"]
        else:
            from ..pipeline import SatQueryPipeline
            pipe = SatQueryPipeline(georeferencer=geo, threshold=0.35, min_pixel_area=15)
            res = pipe.process_pair(
                img_pre=img_pre,
                img_post=img_post,
                image_pair_id=f"pair_sentinel2_{zone_key}",
                timestamp=meta.get("post_datetime", "2023-12-01T00:00:00Z"),
            )
            heatmap = res["heatmap"]
            mask = res["binary_mask"]

        with open(candidates_json, "r", encoding="utf-8") as f:
            candidates_raw = json.load(f)

        # 4. Export Raster GeoTIFF Layers
        p_pre_tif = os.path.join(target_dir, f"{zone_key}_pre_t1.tif")
        p_post_tif = os.path.join(target_dir, f"{zone_key}_post_t2.tif")
        p_heat_tif = os.path.join(target_dir, f"{zone_key}_change_heatmap.tif")
        p_mask_tif = os.path.join(target_dir, f"{zone_key}_binary_mask.tif")

        self.export_geotiff(img_pre, p_pre_tif, geo)
        self.export_geotiff(img_post, p_post_tif, geo)
        self.export_geotiff(heatmap, p_heat_tif, geo)
        self.export_geotiff(mask, p_mask_tif, geo)

        # 5. Export Vector GeoJSON
        p_geojson = os.path.join(target_dir, f"{zone_key}_candidates.geojson")
        self.export_geojson(candidates_raw, p_geojson, geo, zone_name=zone_info["name"])

        # 6. Build Manifest & Affine Metadata
        h, w = img_pre.shape[:2]
        x_min, y_min, _ = geo.pixel_to_local_grid(0, 0)
        x_max, y_max, _ = geo.pixel_to_local_grid(w, h)
        lat_top, lon_left, _ = geo.local_grid_to_geodetic(x_min, y_min)
        lat_bottom, lon_right, _ = geo.local_grid_to_geodetic(x_max, y_max)

        manifest = {
            "zone_key": zone_key,
            "zone_name": zone_info["name"],
            "crs": "EPSG:4326 (WGS 84)",
            "sensor": "ESA Sentinel-2 Level-2A",
            "gsd_meters_per_pixel": [geo.gsd_x, geo.gsd_y],
            "raster_dimensions": {"width_px": w, "height_px": h},
            "spatial_bounding_box": {
                "west_longitude": min(lon_left, lon_right),
                "east_longitude": max(lon_left, lon_right),
                "south_latitude": min(lat_top, lat_bottom),
                "north_latitude": max(lat_top, lat_bottom),
            },
            "affine_transform": {
                "origin_longitude": lon_left,
                "origin_latitude": lat_top,
                "pixel_width_degrees": geo.gsd_x / geo.meters_per_deg_lon,
                "pixel_height_degrees": -(geo.gsd_y / geo.meters_per_deg_lat),
            },
            "exported_files": {
                "pre_imagery_geotiff": os.path.basename(p_pre_tif),
                "post_imagery_geotiff": os.path.basename(p_post_tif),
                "change_heatmap_geotiff": os.path.basename(p_heat_tif),
                "binary_mask_geotiff": os.path.basename(p_mask_tif),
                "candidates_vector_geojson": os.path.basename(p_geojson),
            },
            "candidate_count": len(candidates_raw),
            "qgis_import_guide": {
                "step_1": "Open QGIS and choose Layer -> Add Layer -> Add Raster Layer, select .tif files.",
                "step_2": "For change_heatmap.tif, set Symbology to Singleband Pseudocolor (Color Ramp: Magma or Turbo).",
                "step_3": "Choose Layer -> Add Layer -> Add Vector Layer, select candidates.geojson.",
                "step_4": "Label vector layer by candidate_id and style stroke by uncertainty.",
            },
        }

        p_manifest = os.path.join(target_dir, f"{zone_key}_gis_manifest.json")
        with open(p_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return {
            "zone_key": zone_key,
            "target_dir": target_dir,
            "pre_t1_geotiff": p_pre_tif,
            "post_t2_geotiff": p_post_tif,
            "change_heatmap_geotiff": p_heat_tif,
            "binary_mask_geotiff": p_mask_tif,
            "candidates_geojson": p_geojson,
            "manifest_json": p_manifest,
        }
