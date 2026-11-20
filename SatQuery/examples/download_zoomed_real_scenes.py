#!/usr/bin/env python3
"""CLI utility to download, cache, and analyze zoomed real satellite scenes.

Acquires real Sentinel-2 Level-2A imagery for tightly bounded Indian geographic
hotspots, performs change detection, and outputs visual inspection artifacts
(side-by-side comparison montages, change heatmaps, and close-up chips)
into dedicated directories.

Usage:
    python SatQuery/examples/download_zoomed_real_scenes.py
    python SatQuery/examples/download_zoomed_real_scenes.py --hotspot kanpur_bhauti_nh19
    python SatQuery/examples/download_zoomed_real_scenes.py --force
"""

import argparse
import os
import sys

# Ensure repository root is in python path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from SatQuery.satquery.data.zoomed_scene_loader import (
    ZOOMED_MISSION_HOTSPOTS,
    ZoomedSceneLoader,
)


def main():
    parser = argparse.ArgumentParser(
        description="Download and verify real zoomed bitemporal satellite imagery for Indian hotspots."
    )
    parser.add_argument(
        "--hotspot",
        type=str,
        default="all",
        choices=["all"] + list(ZOOMED_MISSION_HOTSPOTS.keys()),
        help="Specific hotspot identifier to process, or 'all' to process all 5 corridors.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-downloading scenes even if already cached locally.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.32,
        help="Change detection heatmap threshold (default: 0.32).",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=15,
        help="Minimum connected component pixel area (default: 15).",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("🛰️  SATQUERY ZOOMED REAL SATELLITE IMAGERY ACQUISITION & VERIFICATION")
    print("=" * 80)
    print("📡 Sensor:  ESA Sentinel-2 Level-2A (Optical Surface Reflectance)")
    print("🎯 Purpose: High-resolution localized change identification & visual verification")
    print("📁 Storage:")
    print("   • Raw Imagery:    SatQuery/data/zoomed_real_scenes/")
    print("   • Visual Exports: SatQuery/exports/zoomed_change_verification/")
    print("=" * 80)

    loader = ZoomedSceneLoader(repo_root=repo_root)

    keys = (
        list(ZOOMED_MISSION_HOTSPOTS.keys())
        if args.hotspot == "all"
        else [args.hotspot]
    )

    summaries = []
    for idx, key in enumerate(keys, 1):
        info = ZOOMED_MISSION_HOTSPOTS[key]
        print(f"\n[{idx}/{len(keys)}] Processing Corridor: {info['name']} ({key})")
        print(f"    Bounding Box: {info['bbox']}")
        print(f"    GSD: ~{info.get('gsd_m_per_px', 5.0)} m/px | Target: {info['description'][:65]}...")

        try:
            summary = loader.fetch_and_process_hotspot(
                hotspot_key=key,
                image_size=512,
                force_download=args.force,
                threshold=args.threshold,
                min_pixel_area=args.min_area,
            )
            summaries.append(summary)
            print(f"    ✓ Change detection complete: {summary['total_candidates_detected']} targets identified.")
            print(f"    ✓ Total change footprint: {summary['total_change_footprint_ha']} ha ({summary['total_change_footprint_m2']} m²).")
            print(f"    ✓ Top {len(summary['top_inspections'])} close-up chips saved to {key}/inspection_chips/")
        except Exception as e:
            print(f"    ❌ Error processing hotspot {key}: {e}")

    if summaries:
        rep_path = loader.generate_comprehensive_report(summaries)
        print("\n" + "=" * 80)
        print("📊 MULTI-CORRIDOR ZOOMED CHANGE VERIFICATION SUMMARY")
        print("=" * 80)
        for s in summaries:
            print(
                f"• {s['name'][:40]:<40} | Found: {s['total_candidates_detected']:>2} targets | "
                f"Footprint: {s['total_change_footprint_ha']:>5.2f} ha | Shift: ({s['subpixel_shift']['dx_px']}, {s['subpixel_shift']['dy_px']}) px"
            )
        print("-" * 80)
        print(f"📄 Full Visual Analysis Report written to:\n   {rep_path}")
        print("=" * 80)


if __name__ == "__main__":
    main()
