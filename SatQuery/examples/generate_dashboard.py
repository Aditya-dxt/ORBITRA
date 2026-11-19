"""Command-line script to generate the standalone interactive mission operations dashboard.

Produces SatQuery/exports/visualizations/orbitra_mission_dashboard.html
with complete offline interactive wipe swipe, heatmap blending, and candidate inspection.
"""

import argparse
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from SatQuery.satquery.data.dashboard_generator import MissionDashboardGenerator


def main():
    parser = argparse.ArgumentParser(description="Generate ORBITRA Mission Dashboard HTML")
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(REPO_ROOT, "SatQuery", "exports", "visualizations", "orbitra_mission_dashboard.html"),
        help="Destination path for HTML dashboard",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("🛰️  ORBITRA: STANDALONE INTERACTIVE MISSION DASHBOARD GENERATOR")
    print("=" * 80)

    gen = MissionDashboardGenerator(repo_root=REPO_ROOT)
    print("\n🔍 Compiling multi-corridor satellite telemetry and candidate records...")
    out_file = gen.generate_html(output_path=args.output)

    print(f"\n✅ Standalone Mission Operations Dashboard compiled successfully!")
    print(f"   ✓ Dashboard file: {out_file}")
    print("\n💡 Open this file directly in any modern browser (Chrome, Edge, Firefox):")
    print(f"   file:///{out_file.replace(os.sep, '/')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
