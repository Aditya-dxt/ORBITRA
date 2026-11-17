"""Interactive pipeline runner for real Indian satellite change verification missions.

Acquires or loads real bi-temporal Sentinel-2 satellite imagery over Indian mission corridors:
- kanpur_bhauti: Kanpur / Bhauti (UP), NH-19 industrial corridor near PSIT
- bengaluru_tech: Bengaluru / Electronic City IT & infrastructure expansion
- delhi_ncr: New Delhi / Gurugram development corridor
- chennai_sriperumbudur: Chennai / Sriperumbudur manufacturing hub

Executes:
1. Satellite pair loading & 2D phase-correlation spatial alignment
2. Baseline change detection & candidate generation
3. Georeferencing to local metric grid & geodetic coordinates (WGS-84)
4. Calibration and normalized binary Shannon entropy uncertainty
5. Export to agreed schema (v1.0.0-provisional)
6. ARES cross-module policy execution under return-reserve guardrail
7. Visual montage generation
"""

import argparse
import os
import sys
import cv2
import numpy as np
from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

ARES_ROOT = os.path.join(REPO_ROOT, "ARES")
if ARES_ROOT not in sys.path:
    sys.path.insert(0, ARES_ROOT)

from SatQuery.satquery.data.india_satellite_data import INDIAN_MISSION_ZONES, IndiaSatelliteDataLoader
from SatQuery.satquery.pipeline import SatQueryPipeline
from SatQuery.satquery.vision.georeferencing import MissionGeoreferencer
from SatQuery.examples.end_to_end_integration import run_integration


def process_indian_mission(
    zone_key: str = "kanpur_bhauti",
    policy: str = "B3",
    battery_wh: float = 50.0,
    crop_size: int = 512,
    include_human_review: bool = True,
):
    print("=" * 80)
    print("🇮🇳  ORBITRA REAL INDIAN SATELLITE MISSION: SatQuery -> ARES")
    print("=" * 80)

    # 1. Load real Sentinel-2 satellite pair
    loader = IndiaSatelliteDataLoader()
    zone_data = loader.get_indian_scene_pair(zone_key, crop_size=crop_size)

    print(f"\n📍 Region: {zone_data['zone_name']}")
    print(f"   Coordinates: ({zone_data['home_lat']}°N, {zone_data['home_lon']}°E)")
    print(f"   Pre-Change Date (T1):  {zone_data['metadata']['pre_datetime']}")
    print(f"   Post-Change Date (T2): {zone_data['metadata']['post_datetime']}")
    print(f"   Spatial Alignment Shift: dx={zone_data['alignment_shift_pixels'][0]}px, dy={zone_data['alignment_shift_pixels'][1]}px")

    # 2. Configure Georeferencing with native Indian coordinates & Sentinel-2 resolution (10m/px)
    geo = MissionGeoreferencer(
        home_lat=zone_data["home_lat"],
        home_lon=zone_data["home_lon"],
        home_alt=120.0,
        tile_anchor_x=0.0,
        tile_anchor_y=0.0,
        gsd_x=10.0,
        gsd_y=10.0,
        default_flight_alt=60.0,
    )

    # 3. Execute Detection Pipeline
    print("\n🔎 Running SatQuery Change Detection on Real Satellite Imagery...")
    pipeline = SatQueryPipeline(georeferencer=geo, threshold=0.30, min_pixel_area=15)
    pair_id = f"pair_sentinel2_{zone_key}"
    results = pipeline.process_pair(
        img_pre=zone_data["img_pre"],
        img_post=zone_data["img_post"],
        image_pair_id=pair_id,
        timestamp=zone_data["metadata"]["post_datetime"],
    )

    candidates = results["candidates"]
    print(f"   ✓ Generated {len(candidates)} candidate change records.")

    # 4. Export Candidate Records
    export_path = os.path.join(REPO_ROOT, "SatQuery", "exports", f"candidates_{zone_key}.json")
    pipeline.export_candidates_to_json(candidates, export_path)
    print(f"   ✓ Exported schema-compliant candidates to: {export_path}")

    # 5. Generate Visual Montage
    vis_dir = os.path.join(REPO_ROOT, "SatQuery", "exports", "visualizations")
    os.makedirs(vis_dir, exist_ok=True)
    vis_path = os.path.join(vis_dir, f"{zone_key}_real_montage.png")

    img_pre = zone_data["img_pre"]
    img_post = zone_data["img_post"]
    heatmap = results["heatmap"]
    mask = results["binary_mask"]

    annotated = img_post.copy()
    for cand in candidates:
        if cand.region.bbox_pixels:
            x1, y1, x2, y2 = cand.region.bbox_pixels
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 60, 0), 2)
            label = f"{cand.candidate_id} p={cand.confidence:.2f}"
            cv2.putText(annotated, label, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)

    heatmap_uint8 = (heatmap * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

    h, w = img_pre.shape[:2]
    montage = np.zeros((h, w * 4, 3), dtype=np.uint8)
    montage[:, :w] = img_pre
    montage[:, w : w * 2] = img_post
    montage[:, w * 2 : w * 3] = heatmap_rgb
    montage[:, w * 3 :] = annotated

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(montage, f"Real T1 ({zone_data['metadata']['pre_datetime'][:10]})", (10, 25), font, 0.5, (255, 255, 255), 1)
    cv2.putText(montage, f"Real T2 ({zone_data['metadata']['post_datetime'][:10]})", (w + 10, 25), font, 0.5, (255, 255, 255), 1)
    cv2.putText(montage, "Change Heatmap", (w * 2 + 10, 25), font, 0.5, (255, 255, 255), 1)
    cv2.putText(montage, f"Detections ({len(candidates)})", (w * 3 + 10, 25), font, 0.5, (0, 255, 255), 1)

    Image.fromarray(montage).save(vis_path)
    print(f"   ✓ Visual montage saved to: {vis_path}")

    # 6. Run ARES Decision Engine Integration
    report_out = os.path.join(REPO_ROOT, "SatQuery", "exports", f"mission_report_{zone_key}.json")
    run_integration(
        candidates_json_path=export_path,
        policy_name=policy,
        battery_wh=battery_wh,
        export_report_path=report_out,
        include_human_review=include_human_review,
    )


def main():
    parser = argparse.ArgumentParser(description="ORBITRA Real Indian Satellite Mission Runner")
    parser.add_argument(
        "--zone",
        type=str,
        default="kanpur_bhauti",
        choices=list(INDIAN_MISSION_ZONES.keys()),
        help="Indian geographic mission zone",
    )
    parser.add_argument("--policy", type=str, default="B3", choices=["B0", "B1", "B2", "B3", "B4"])
    parser.add_argument("--battery_wh", type=float, default=50.0)
    parser.add_argument("--no-human-review", action="store_true", help="Exclude HUMAN_REVIEW from action space, forcing flight/model triage")
    args = parser.parse_args()

    process_indian_mission(
        zone_key=args.zone,
        policy=args.policy,
        battery_wh=args.battery_wh,
        include_human_review=not args.no_human_review,
    )


if __name__ == "__main__":
    main()
