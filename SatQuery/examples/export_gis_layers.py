"""Command-line script to export GeoTIFF and GeoJSON GIS layers for ORBITRA mission zones.

Generates full GIS packs for QGIS, ArcGIS, and Google Earth Engine ingestion:
- T1 Pre-change GeoTIFF (.tif)
- T2 Post-change GeoTIFF (.tif)
- Change Heatmap GeoTIFF (.tif)
- Binary Mask GeoTIFF (.tif)
- Candidate Vector Polygons GeoJSON (.geojson)
- GIS Manifest & Import Guide (.json)
"""

import argparse
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from SatQuery.satquery.data.india_satellite_data import INDIAN_MISSION_ZONES
from SatQuery.satquery.vision.gis_export import GISExporter


def main():
    parser = argparse.ArgumentParser(description="Export ORBITRA GIS GeoTIFF and GeoJSON Layers")
    parser.add_argument(
        "--zone",
        type=str,
        default="all",
        choices=["all"] + list(INDIAN_MISSION_ZONES.keys()),
        help="Target mission corridor ('all' exports all 4 Indian corridors)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(REPO_ROOT, "SatQuery", "exports", "gis"),
        help="Destination directory for GIS packages",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("🌍 ORBITRA: NATIVE GIS & GEOTIFF EXPORTER")
    print("=" * 80)

    exporter = GISExporter(output_root=args.output_dir)
    target_zones = list(INDIAN_MISSION_ZONES.keys()) if args.zone == "all" else [args.zone]

    for z_key in target_zones:
        z_name = INDIAN_MISSION_ZONES[z_key]["name"]
        print(f"\n📦 Exporting GIS Pack for Corridor: [{z_key}] - {z_name}")
        pack = exporter.export_mission_gis_pack(z_key)
        print(f"   ✓ Pre-change GeoTIFF:    {os.path.basename(pack['pre_t1_geotiff'])}")
        print(f"   ✓ Post-change GeoTIFF:   {os.path.basename(pack['post_t2_geotiff'])}")
        print(f"   ✓ Change Heatmap GeoTIFF:{os.path.basename(pack['change_heatmap_geotiff'])}")
        print(f"   ✓ Binary Mask GeoTIFF:   {os.path.basename(pack['binary_mask_geotiff'])}")
        print(f"   ✓ Candidates GeoJSON:    {os.path.basename(pack['candidates_geojson'])}")
        print(f"   ✓ GIS Manifest & Guide:  {os.path.basename(pack['manifest_json'])}")

    print("\n" + "=" * 80)
    print(f"✅ Successfully exported GIS packages to: {args.output_dir}")
    print("   All layers ready for direct drag-and-drop ingestion into QGIS & ArcGIS Pro.")
    print("=" * 80)


if __name__ == "__main__":
    main()
