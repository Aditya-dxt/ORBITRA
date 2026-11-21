#!/usr/bin/env python3
"""CLI utility to download, stitch, and analyze sub-meter high-resolution satellite imagery.

Fetches authentic 0.59 m/pixel (Zoom Level 18) orthophotography from the Esri Wayback
historical archive for Indian strategic hotspots, performs change detection, and outputs
crystal-clear visual inspection maps (4-panel Ultra-HD montages, annotated detections,
and close-up building chips) that remain razor-sharp when zoomed in.

Usage:
    python SatQuery/examples/download_submeter_highres_scenes.py
    python SatQuery/examples/download_submeter_highres_scenes.py --hotspot kanpur_bhauti_psit
    python SatQuery/examples/download_submeter_highres_scenes.py --force
"""

import argparse
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from SatQuery.satquery.data.submeter_highres_loader import (
    SUBMETER_HOTSPOTS,
    SubmeterHighresSceneLoader,
)


def main():
    parser = argparse.ArgumentParser(
        description="Download and verify sub-meter high-resolution bitemporal satellite imagery."
    )
    parser.add_argument(
        "--hotspot",
        type=str,
        default="all",
        choices=["all"] + list(SUBMETER_HOTSPOTS.keys()),
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
        default=0.28,
        help="Change detection heatmap threshold (default: 0.28).",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=25,
        help="Minimum connected component pixel area (default: 25).",
    )

    args = parser.parse_args()

    print("=" * 85)
    print("🛰️  SATQUERY SUB-METER HIGH-RESOLUTION SATELLITE CHANGE VERIFICATION (0.59 m/pixel)")
    print("=" * 85)
    print("📡 Sensor:  Esri World Imagery Wayback Archive (Maxar WorldView / Aerial Ortho)")
    print("🔍 Detail:  Zoom Level 18 (GSD = 0.59 m/pixel) — Crisp & Sharp Without Zoom Blur")
    print("📁 Storage:")
    print("   • Raw Imagery:    SatQuery/data/submeter_highres_scenes/")
    print("   • Visual Exports: SatQuery/exports/submeter_change_verification/")
    print("=" * 85)

    loader = SubmeterHighresSceneLoader(repo_root=repo_root)

    keys = (
        list(SUBMETER_HOTSPOTS.keys())
        if args.hotspot == "all"
        else [args.hotspot]
    )

    summaries = []
    for idx, key in enumerate(keys, 1):
        info = SUBMETER_HOTSPOTS[key]
        print(f"\n[{idx}/{len(keys)}] Processing Corridor: {info['name']} ({key})")
        print(f"    Center: ({info['home_lat']}, {info['home_lon']}) | Resolution: {info['gsd_m_per_px']} m/px")
        print(f"    Epochs: {info['pre_date']} (Rel {info['pre_release']}) -> {info['post_date']} (Rel {info['post_release']})")

        try:
            summary = loader.fetch_and_process_hotspot(
                hotspot_key=key,
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
        print("\n" + "=" * 85)
        print("📊 MULTI-CORRIDOR SUB-METER CHANGE VERIFICATION SUMMARY")
        print("=" * 85)
        for s in summaries:
            print(
                f"• {s['name'][:38]:<38} | {s['total_candidates_detected']:>3} targets | "
                f"Footprint: {s['total_change_footprint_ha']:>5.2f} ha | Shift: ({s['subpixel_shift']['dx_px']}, {s['subpixel_shift']['dy_px']}) px"
            )
        print("-" * 85)
        print(f"📄 Full Visual Analysis Report written to:\n   {rep_path}")
        print("=" * 85)


if __name__ == "__main__":
    main()
