"""Executable script to generate the complete Multi-Zone Indian Satellite Mission Gallery.

Validates all four Indian mission corridors (Kanpur, Delhi NCR, Bengaluru, Chennai),
extracts inspection chips, produces the JSON catalog, vector SVG overview, and markdown documentation.
"""

import argparse
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from SatQuery.satquery.data.mission_gallery import MissionGalleryGenerator


def main():
    parser = argparse.ArgumentParser(description="Generate ORBITRA Multi-Zone Indian Mission Gallery")
    parser.add_argument("--chips", action="store_true", default=True, help="Extract visual candidate chips")
    parser.add_argument("--no-chips", dest="chips", action="store_false", help="Skip chip extraction")
    parser.add_argument("--max-chips", type=int, default=4, help="Max chips to extract per zone")
    args = parser.parse_args()

    print("=" * 80)
    print("🇮🇳  ORBITRA: MULTI-ZONE INDIAN SATELLITE MISSION GALLERY GENERATOR")
    print("=" * 80)

    generator = MissionGalleryGenerator(repo_root=REPO_ROOT)
    print("\n🔍 Validating candidate sets and building mission gallery...")
    gallery_data = generator.build_gallery(generate_chips=args.chips, max_chips_per_zone=args.max_chips)

    print(f"\n📊 Aggregate Mission Results:")
    agg = gallery_data["aggregate_statistics"]
    print(f"   • Operational Zones:          {gallery_data['total_zones']}")
    print(f"   • Total Candidates Detected:  {agg['total_candidates']}")
    print(f"   • Total Change Footprint:     {agg['total_change_area_hectares']} ha ({int(agg['total_change_area_m2']):,} m²)")
    print(f"   • Mean Calibrated Confidence: {agg['mean_confidence']:.4f}")
    print(f"   • Mean Shannon Uncertainty:   {agg['mean_uncertainty']:.4f}")

    print("\n🗺️  Per-Zone Breakdown:")
    for z_key, z in gallery_data["mission_zones"].items():
        m = z["candidate_metrics"]
        print(f"   📍 [{z_key.upper()}]: {z['name']}")
        print(f"      - Period: {z['pre_observation']['datetime'][:10]} -> {z['post_observation']['datetime'][:10]}")
        print(f"      - Candidates: {m['total_candidates']} | Area: {m['total_change_footprint_ha']} ha | Mean Conf: {m['mean_confidence']:.3f} | Mean Unc: {m['mean_uncertainty']:.3f}")

    print("\n🎨 Generating Vector SVG Overview Graphic...")
    svg_path = generator.generate_gallery_svg(gallery_data)
    print(f"   ✓ Vector SVG written to: {svg_path}")

    print("\n📖 Generating Comprehensive Markdown Mission Gallery Document...")
    md_path = generator.generate_gallery_markdown(gallery_data)
    print(f"   ✓ Markdown gallery written to: {md_path}")

    print("\n" + "=" * 80)
    print("✅ Mission Gallery Generation Complete & Verified against Schema v1.0.0")
    print("=" * 80)


if __name__ == "__main__":
    main()
