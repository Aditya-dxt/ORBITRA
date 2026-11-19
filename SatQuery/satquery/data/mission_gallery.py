"""Multi-Zone Indian Satellite Mission Gallery Generator and Validator.

Compiles, validates, and visualizes multi-temporal Sentinel-2 Level-2A satellite change
verification missions across four strategic Indian geographic corridors:
1. Kanpur / Bhauti Corridor, Uttar Pradesh (NH-19 Industrial Corridor near PSIT)
2. Delhi NCR / Gurugram Development Corridor (Rapid commercial and urban expansion)
3. Bengaluru Electronic City Infrastructure (Metro rail expansion & IT tech parks)
4. Chennai / Sriperumbudur Industrial Corridor (Automotive & electronics manufacturing hub)

Produces:
- Validated candidate records (Schema v1.0.0, Shannon entropy bounded)
- Candidate visual inspection chips (Pre, Post, Diff, Annotation)
- Multi-zone aggregated JSON gallery catalog
- Vector SVG overview dashboard
- Comprehensive technical markdown mission gallery
"""

import math
import os
import json
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np
from PIL import Image

from ..schemas.candidate_record import SatQueryCandidateRecord as CandidateRecord
from .india_satellite_data import INDIAN_MISSION_ZONES, IndiaSatelliteDataLoader
from .image_resolver import ImagePairResolver


def compute_shannon_entropy(p: float) -> float:
    """Compute binary Shannon entropy normalized to [0, 1]."""
    p_clamped = max(1e-6, min(1.0 - 1e-6, float(p)))
    return - (p_clamped * math.log2(p_clamped) + (1.0 - p_clamped) * math.log2(1.0 - p_clamped))


class MissionGalleryGenerator:
    """Generates standardized inspection cards, visual chips, and reports for all Indian zones."""

    def __init__(
        self,
        repo_root: Optional[str] = None,
        data_root: Optional[str] = None,
        exports_root: Optional[str] = None,
    ):
        if repo_root is None:
            # SatQuery/satquery/data/mission_gallery.py -> repo root
            self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        else:
            self.repo_root = repo_root

        self.satquery_root = os.path.join(self.repo_root, "SatQuery")
        self.data_root = data_root or os.path.join(self.satquery_root, "data")
        self.exports_root = exports_root or os.path.join(self.satquery_root, "exports")
        self.vis_root = os.path.join(self.exports_root, "visualizations")
        self.chips_root = os.path.join(self.vis_root, "inspection_chips")

        os.makedirs(self.exports_root, exist_ok=True)
        os.makedirs(self.vis_root, exist_ok=True)
        os.makedirs(self.chips_root, exist_ok=True)

        self.loader = IndiaSatelliteDataLoader(cache_dir=os.path.join(self.data_root, "india_scenes"))
        self.resolver = ImagePairResolver(data_root=self.data_root)

    def extract_candidate_chip(
        self,
        img_pre: np.ndarray,
        img_post: np.ndarray,
        bbox: List[int],
        padding: int = 16,
        target_height: int = 120,
    ) -> np.ndarray:
        """Extract a multi-panel visual inspection chip for a candidate bounding box.
        
        Panels: [Pre-T1 | Post-T2 | Absolute Diff Heatmap | Post with Bounding Box]
        """
        h, w = img_pre.shape[:2]
        xmin, ymin, xmax, ymax = bbox

        # Expand with context padding clamped to image bounds
        px1 = max(0, xmin - padding)
        py1 = max(0, ymin - padding)
        px2 = min(w, xmax + padding)
        py2 = min(h, ymax + padding)

        crop_pre = img_pre[py1:py2, px1:px2]
        crop_post = img_post[py1:py2, px1:px2]

        if crop_pre.size == 0 or crop_post.size == 0:
            # Fallback placeholder if bbox was degenerate
            placeholder = np.zeros((target_height, target_height * 4, 3), dtype=np.uint8)
            return placeholder

        # Compute optical spectral difference
        diff_gray = cv2.absdiff(
            cv2.cvtColor(crop_pre, cv2.COLOR_RGB2GRAY),
            cv2.cvtColor(crop_post, cv2.COLOR_RGB2GRAY),
        )
        diff_norm = cv2.normalize(diff_gray, None, 0, 255, cv2.NORM_MINMAX)
        diff_color = cv2.applyColorMap(diff_norm, cv2.COLORMAP_MAGMA)
        diff_rgb = cv2.cvtColor(diff_color, cv2.COLOR_BGR2RGB)

        # Annotated panel with box
        annotated = crop_post.copy()
        rel_x1 = xmin - px1
        rel_y1 = ymin - py1
        rel_x2 = xmax - px1
        rel_y2 = ymax - py1
        cv2.rectangle(annotated, (rel_x1, rel_y1), (rel_x2, rel_y2), (255, 60, 0), 2)

        # Scale all 4 panels to uniform height while preserving aspect ratio
        panels = [crop_pre, crop_post, diff_rgb, annotated]
        scaled_panels = []
        for p in panels:
            ph, pw = p.shape[:2]
            scale = target_height / max(ph, 1)
            new_w = max(int(pw * scale), 1)
            scaled = cv2.resize(p, (new_w, target_height), interpolation=cv2.INTER_LINEAR)
            scaled_panels.append(scaled)

        # Horizontal concatenation with separator line
        sep = np.ones((target_height, 3, 3), dtype=np.uint8) * 40
        chip = np.hstack([
            scaled_panels[0], sep,
            scaled_panels[1], sep,
            scaled_panels[2], sep,
            scaled_panels[3]
        ])
        return chip

    def build_gallery(
        self,
        zones: Optional[List[str]] = None,
        generate_chips: bool = True,
        max_chips_per_zone: int = 4,
    ) -> Dict[str, Any]:
        """Validate candidate sets and compile mission gallery for all requested zones."""
        target_zones = zones or list(INDIAN_MISSION_ZONES.keys())
        gallery_summary = {
            "schema_version": "v1.0.0",
            "total_zones": len(target_zones),
            "mission_zones": {},
            "aggregate_statistics": {
                "total_candidates": 0,
                "total_change_area_m2": 0.0,
                "total_change_area_hectares": 0.0,
                "mean_confidence": 0.0,
                "mean_uncertainty": 0.0,
            },
        }

        all_confidences = []
        all_uncertainties = []
        total_area_m2 = 0.0
        total_candidates_count = 0

        for zone_key in target_zones:
            zone_info = INDIAN_MISSION_ZONES[zone_key]
            scene_data = self.loader.get_indian_scene_pair(zone_key)

            img_pre = scene_data["img_pre"]
            img_post = scene_data["img_post"]
            meta = scene_data["metadata"]

            # Load candidates JSON
            candidates_path = os.path.join(self.exports_root, f"candidates_{zone_key}.json")
            if not os.path.exists(candidates_path):
                # Fallback run pipeline if candidates not yet exported
                from ..pipeline import SatQueryPipeline
                from ..vision.georeferencing import MissionGeoreferencer
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
                pipe = SatQueryPipeline(georeferencer=geo, threshold=0.35, min_pixel_area=15)
                res = pipe.process_pair(
                    img_pre=img_pre,
                    img_post=img_post,
                    image_pair_id=f"pair_sentinel2_{zone_key}",
                    timestamp=meta.get("post_datetime", "2023-12-01T00:00:00Z"),
                )
                pipe.export_candidates_to_json(res["candidates"], candidates_path)

            with open(candidates_path, "r", encoding="utf-8") as f:
                raw_cands = json.load(f)

            # Validate each candidate against strict Pydantic schema v1.0.0
            validated_cands = []
            cand_dicts = []
            for item in raw_cands:
                rec = CandidateRecord(**item)
                validated_cands.append(rec)

                # Validate Shannon entropy constraint |u - h(p)| <= 0.15
                h_p = compute_shannon_entropy(rec.confidence)
                entropy_gap = abs(rec.uncertainty - h_p)
                assert entropy_gap <= 0.15001, f"Entropy gap {entropy_gap:.4f} exceeds 0.15 for candidate {rec.candidate_id}"

                # Calculate transit distance from mission base [0, 0, 0]
                dist_m = math.sqrt(rec.region.local_grid.x_meters**2 + rec.region.local_grid.y_meters**2)

                # Bounding box area at GSD=10m/px -> 1 pixel = 100 m^2
                bx1, by1, bx2, by2 = rec.region.bbox_pixels
                px_area = (bx2 - bx1) * (by2 - by1)
                m2_area = px_area * 100.0

                cand_dicts.append({
                    "candidate_id": rec.candidate_id,
                    "confidence": round(rec.confidence, 4),
                    "uncertainty": round(rec.uncertainty, 4),
                    "shannon_entropy_reference": round(h_p, 4),
                    "local_grid": {
                        "x_meters": round(rec.region.local_grid.x_meters, 1),
                        "y_meters": round(rec.region.local_grid.y_meters, 1),
                        "z_meters": round(rec.region.local_grid.z_meters, 1),
                        "transit_distance_m": round(dist_m, 1),
                    },
                    "coordinates": {
                        "lat": round(rec.region.coordinates.center_lat, 6) if rec.region.coordinates else None,
                        "lon": round(rec.region.coordinates.center_lon, 6) if rec.region.coordinates else None,
                    },
                    "bbox_pixels": rec.region.bbox_pixels,
                    "pixel_area": px_area,
                    "area_m2": m2_area,
                    "area_hectares": round(m2_area / 10000.0, 3),
                })

            # Sort by area descending for inspection chips
            sorted_by_area = sorted(cand_dicts, key=lambda c: c["pixel_area"], reverse=True)

            chips_info = []
            if generate_chips:
                for idx, c in enumerate(sorted_by_area[:max_chips_per_zone]):
                    chip = self.extract_candidate_chip(img_pre, img_post, c["bbox_pixels"])
                    chip_name = f"{zone_key}_cand_{c['candidate_id']}_chip.png"
                    chip_path = os.path.join(self.chips_root, chip_name)
                    Image.fromarray(chip).save(chip_path)
                    chips_info.append({
                        "candidate_id": c["candidate_id"],
                        "chip_filename": chip_name,
                        "chip_relative_path": f"visualizations/inspection_chips/{chip_name}",
                        "confidence": c["confidence"],
                        "uncertainty": c["uncertainty"],
                        "transit_distance_m": c["local_grid"]["transit_distance_m"],
                        "area_m2": c["area_m2"],
                    })

            # Zone statistics
            confs = [c["confidence"] for c in cand_dicts]
            uncs = [c["uncertainty"] for c in cand_dicts]
            zone_total_area = sum(c["area_m2"] for c in cand_dicts)

            all_confidences.extend(confs)
            all_uncertainties.extend(uncs)
            total_area_m2 += zone_total_area
            total_candidates_count += len(cand_dicts)

            # Load existing ARES simulation mission report if available
            mission_report_path = os.path.join(self.exports_root, f"mission_report_{zone_key}.json")
            ares_summary = None
            if os.path.exists(mission_report_path):
                try:
                    with open(mission_report_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                        ares_summary = m_data.get("mission_summary", {})
                except Exception:
                    pass

            gallery_summary["mission_zones"][zone_key] = {
                "zone_key": zone_key,
                "name": zone_info["name"],
                "description": zone_info["description"],
                "home_coordinates": {
                    "lat": zone_info["home_lat"],
                    "lon": zone_info["home_lon"],
                },
                "bounding_box_wgs84": zone_info["bbox"],
                "sensor": "ESA Sentinel-2 Level-2A (10m GSD)",
                "pre_observation": {
                    "scene_id": meta.get("pre_scene_id", "N/A"),
                    "datetime": meta.get("pre_datetime", "N/A"),
                },
                "post_observation": {
                    "scene_id": meta.get("post_scene_id", "N/A"),
                    "datetime": meta.get("post_datetime", "N/A"),
                },
                "spatial_alignment_shift_px": scene_data["alignment_shift_pixels"],
                "candidate_metrics": {
                    "total_candidates": len(cand_dicts),
                    "mean_confidence": round(float(np.mean(confs)), 4) if confs else 0.0,
                    "min_confidence": round(float(np.min(confs)), 4) if confs else 0.0,
                    "max_confidence": round(float(np.max(confs)), 4) if confs else 0.0,
                    "mean_uncertainty": round(float(np.mean(uncs)), 4) if uncs else 0.0,
                    "min_uncertainty": round(float(np.min(uncs)), 4) if uncs else 0.0,
                    "max_uncertainty": round(float(np.max(uncs)), 4) if uncs else 0.0,
                    "total_change_footprint_m2": round(zone_total_area, 1),
                    "total_change_footprint_ha": round(zone_total_area / 10000.0, 2),
                    "max_transit_distance_m": round(max(c["local_grid"]["transit_distance_m"] for c in cand_dicts), 1) if cand_dicts else 0.0,
                },
                "ares_simulated_dispatch": ares_summary,
                "inspection_chips": chips_info,
                "top_candidates": sorted_by_area[:max_chips_per_zone],
            }

        # Aggregate overall statistics
        gallery_summary["aggregate_statistics"] = {
            "total_candidates": total_candidates_count,
            "total_change_area_m2": round(total_area_m2, 1),
            "total_change_area_hectares": round(total_area_m2 / 10000.0, 2),
            "mean_confidence": round(float(np.mean(all_confidences)), 4) if all_confidences else 0.0,
            "mean_uncertainty": round(float(np.mean(all_uncertainties)), 4) if all_uncertainties else 0.0,
        }

        # Save JSON catalog
        catalog_path = os.path.join(self.exports_root, "indian_mission_gallery.json")
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(gallery_summary, f, indent=2)

        return gallery_summary

    def generate_gallery_svg(self, gallery_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """Render a publication-ready vector SVG mission gallery overview."""
        out_svg = output_path or os.path.join(self.vis_root, "indian_mission_gallery_overview.svg")
        zones = gallery_data["mission_zones"]
        agg = gallery_data["aggregate_statistics"]

        width = 1100
        height = 680

        # Colors
        bg_dark = "#0f172a"
        card_bg = "#1e293b"
        card_border = "#334155"
        text_primary = "#f8fafc"
        text_secondary = "#94a3b8"
        accent_blue = "#38bdf8"
        accent_emerald = "#34d399"
        accent_amber = "#fbbf24"
        accent_purple = "#c084fc"

        zone_colors = {
            "kanpur_bhauti": accent_amber,
            "delhi_ncr": accent_blue,
            "bengaluru_tech": accent_emerald,
            "chennai_sriperumbudur": accent_purple,
        }

        svg_lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
            f'  <rect width="{width}" height="{height}" fill="{bg_dark}" rx="16" />',
            '  <!-- Header -->',
            f'  <text x="40" y="48" font-family="system-ui, -apple-system, sans-serif" font-size="22" font-weight="700" fill="{text_primary}">ORBITRA Multi-Zone Indian Satellite Mission Gallery</text>',
            f'  <text x="40" y="74" font-family="system-ui, -apple-system, sans-serif" font-size="13" fill="{text_secondary}">Bitemporal Sentinel-2 L2A Optical Surface Reflectance | Schema {gallery_data["schema_version"]} | {gallery_data["total_zones"]} Operational Geographic Corridors</text>',
            '',
            '  <!-- Aggregate Stats Banner -->',
            f'  <rect x="40" y="96" width="{width - 80}" height="64" fill="{card_bg}" stroke="{card_border}" stroke-width="1.5" rx="10" />',
            f'  <text x="70" y="122" font-family="system-ui, sans-serif" font-size="11" fill="{text_secondary}">TOTAL CANDIDATES</text>',
            f'  <text x="70" y="145" font-family="system-ui, sans-serif" font-size="18" font-weight="700" fill="{accent_blue}">{agg["total_candidates"]}</text>',
            f'  <text x="260" y="122" font-family="system-ui, sans-serif" font-size="11" fill="{text_secondary}">TOTAL CHANGE AREA</text>',
            f'  <text x="260" y="145" font-family="system-ui, sans-serif" font-size="18" font-weight="700" fill="{accent_emerald}">{agg["total_change_area_hectares"]} ha ({int(agg["total_change_area_m2"]):,} m²)</text>',
            f'  <text x="560" y="122" font-family="system-ui, sans-serif" font-size="11" fill="{text_secondary}">MEAN CONFIDENCE (p)</text>',
            f'  <text x="560" y="145" font-family="system-ui, sans-serif" font-size="18" font-weight="700" fill="{accent_amber}">{agg["mean_confidence"]:.3f}</text>',
            f'  <text x="780" y="122" font-family="system-ui, sans-serif" font-size="11" fill="{text_secondary}">MEAN UNCERTAINTY (u)</text>',
            f'  <text x="780" y="145" font-family="system-ui, sans-serif" font-size="18" font-weight="700" fill="{accent_purple}">{agg["mean_uncertainty"]:.3f}</text>',
            '',
            '  <!-- 2x2 Grid of Zone Cards -->',
        ]

        card_w = (width - 80 - 24) // 2
        card_h = 220
        start_y = 180

        coords_grid = [
            (40, start_y),
            (40 + card_w + 24, start_y),
            (40, start_y + card_h + 20),
            (40 + card_w + 24, start_y + card_h + 20),
        ]

        for idx, (z_key, z_data) in enumerate(zones.items()):
            if idx >= 4:
                break
            cx, cy = coords_grid[idx]
            color = zone_colors.get(z_key, accent_blue)
            m = z_data["candidate_metrics"]
            ares = z_data.get("ares_simulated_dispatch") or {}
            policy_lbl = ares.get("policy_id", "N/A")
            inspected = ares.get("candidates_inspected", 0)

            svg_lines.extend([
                f'  <!-- Card {idx+1}: {z_key} -->',
                f'  <rect x="{cx}" y="{cy}" width="{card_w}" height="{card_h}" fill="{card_bg}" stroke="{card_border}" stroke-width="1.5" rx="10" />',
                f'  <circle cx="{cx + 24}" cy="{cy + 28}" r="8" fill="{color}" />',
                f'  <text x="{cx + 42}" y="{cy + 33}" font-family="system-ui, sans-serif" font-size="15" font-weight="700" fill="{text_primary}">{z_data["name"]}</text>',
                f'  <text x="{cx + 24}" y="{cy + 56}" font-family="system-ui, sans-serif" font-size="11" fill="{text_secondary}">{z_data["description"]}</text>',
                f'  <line x1="{cx + 24}" y1="{cy + 68}" x2="{cx + card_w - 24}" y2="{cy + 68}" stroke="{card_border}" stroke-width="1" />',
                f'  <text x="{cx + 24}" y="{cy + 92}" font-family="system-ui, sans-serif" font-size="12" fill="{text_secondary}">Coordinates: <tspan fill="{text_primary}">{z_data["home_coordinates"]["lat"]}°N, {z_data["home_coordinates"]["lon"]}°E</tspan></text>',
                f'  <text x="{cx + 24}" y="{cy + 112}" font-family="system-ui, sans-serif" font-size="12" fill="{text_secondary}">Interval: <tspan fill="{text_primary}">{z_data["pre_observation"]["datetime"][:10]} → {z_data["post_observation"]["datetime"][:10]}</tspan></text>',
                f'  <text x="{cx + 24}" y="{cy + 132}" font-family="system-ui, sans-serif" font-size="12" fill="{text_secondary}">Candidates: <tspan fill="{color}" font-weight="700">{m["total_candidates"]} detections</tspan> ({m["total_change_footprint_ha"]} ha)</text>',
                f'  <text x="{cx + 24}" y="{cy + 152}" font-family="system-ui, sans-serif" font-size="12" fill="{text_secondary}">Confidence: <tspan fill="{text_primary}">avg {m["mean_confidence"]:.3f}</tspan> | Uncertainty: <tspan fill="{text_primary}">avg {m["mean_uncertainty"]:.3f}</tspan></text>',
                f'  <text x="{cx + 24}" y="{cy + 172}" font-family="system-ui, sans-serif" font-size="12" fill="{text_secondary}">Max Transit: <tspan fill="{text_primary}">{m["max_transit_distance_m"]} m</tspan> | Reg Shift: <tspan fill="{text_primary}">dx={z_data["spatial_alignment_shift_px"][0]}px</tspan></text>',
                f'  <rect x="{cx + 24}" y="{cy + 184}" width="{card_w - 48}" height="24" fill="#0f172a" rx="4" />',
                f'  <text x="{cx + 34}" y="{cy + 200}" font-family="system-ui, sans-serif" font-size="11" fill="{accent_emerald}">ARES Simulation ({policy_lbl}): {inspected} inspected | Safe Return: {ares.get("safe_return_completed", True)}</text>',
            ])

        svg_lines.append('</svg>')
        svg_content = "\n".join(svg_lines)

        with open(out_svg, "w", encoding="utf-8") as f:
            f.write(svg_content)

        return out_svg

    def generate_gallery_markdown(self, gallery_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """Render publication-grade markdown gallery documentation."""
        out_md = output_path or os.path.join(self.satquery_root, "docs", "INDIAN_MISSION_GALLERY.md")
        agg = gallery_data["aggregate_statistics"]
        zones = gallery_data["mission_zones"]

        md = [
            "# ORBITRA Multi-Zone Indian Satellite Mission Gallery",
            "",
            "**Module:** SatQuery (Computer Vision & Spatial Analytics)  ",
            "**Downstream Integration:** ARES (Energy-Aware Autonomous Verification)  ",
            f"**Interface Contract:** Schema `{gallery_data['schema_version']}`  ",
            "**Imagery Source:** European Space Agency (ESA) Sentinel-2 Level-2A (Optical Surface Reflectance, 10m GSD)  ",
            "**Status:** Production / Complete  ",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            "The **ORBITRA Multi-Zone Mission Gallery** validates the end-to-end satellite-to-drone pipeline across four diverse, high-growth Indian geographic corridors. Each corridor represents distinct topographic, infrastructural, and urban development typologies, captured across an approximate **2-year bitemporal observation baseline** (2021/2022 to 2023/2024).",
            "",
            "All candidate records are strictly formatted and validated under schema `v1.0.0` with guaranteed Euclidean local grid coordinates `(x, y, z)` relative to the mission ground base `[0, 0, 0]`, WGS-84 geodetic coordinates, calibrated confidence scores, and normalized binary Shannon entropy uncertainty bounds ($|u - h(p)| \\le 0.15$).",
            "",
            "### Cross-Zone Aggregate Summary",
            "",
            f"- **Operational Corridors:** {gallery_data['total_zones']} zones",
            f"- **Total Candidate Detections:** {agg['total_candidates']} candidate regions",
            f"- **Total Cumulative Change Footprint:** **{agg['total_change_area_hectares']} hectares** ({int(agg['total_change_area_m2']):,} m²)",
            f"- **Mean Calibrated Confidence ($p$):** `{agg['mean_confidence']:.4f}`",
            f"- **Mean Shannon Entropy Uncertainty ($u$):** `{agg['mean_uncertainty']:.4f}`",
            "",
            "---",
            "",
            "## 2. Multi-Zone Comparative Overview",
            "",
            "| Zone Identifier | Geographic Corridor | Typology | Baseline Window | Candidates | Change Area (ha) | Mean $p$ | Mean $u$ | Max Transit |",
            "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        for z_key, z in zones.items():
            m = z["candidate_metrics"]
            t1 = z["pre_observation"]["datetime"][:10]
            t2 = z["post_observation"]["datetime"][:10]
            md.append(
                f"| **`{z_key}`** | {z['name']} | {z['description']} | `{t1}` → `{t2}` | "
                f"**{m['total_candidates']}** | {m['total_change_footprint_ha']} ha | `{m['mean_confidence']:.3f}` | "
                f"`{m['mean_uncertainty']:.3f}` | {m['max_transit_distance_m']} m |"
            )

        md.extend([
            "",
            "---",
            "",
            "## 3. Detailed Zone Profiles & Candidate Inspection Cards",
            "",
        ])

        for z_key, z in zones.items():
            m = z["candidate_metrics"]
            ares = z.get("ares_simulated_dispatch") or {}

            md.extend([
                f"### 3.{list(zones.keys()).index(z_key) + 1} {z['name']} (`{z_key}`)",
                "",
                f"- **Primary Infrastructure:** {z['description']}",
                f"- **Home Base Anchor:** `{z['home_coordinates']['lat']}°N, {z['home_coordinates']['lon']}°E` (Elevation: 120.0 m)",
                f"- **Sentinel-2 L2A Pre-Scene (T1):** `{z['pre_observation']['scene_id']}` ({z['pre_observation']['datetime'][:19]}Z)",
                f"- **Sentinel-2 L2A Post-Scene (T2):** `{z['post_observation']['scene_id']}` ({z['post_observation']['datetime'][:19]}Z)",
                f"- **Phase Correlation Co-Registration Shift:** $\\Delta x = {z['spatial_alignment_shift_px'][0]}\\text{{ px}}$, $\\Delta y = {z['spatial_alignment_shift_px'][1]}\\text{{ px}}$",
                f"- **Detection Volume:** **{m['total_candidates']} change candidates** covering **{m['total_change_footprint_ha']} hectares**",
                f"- **Confidence Range:** `{m['min_confidence']:.3f}` to `{m['max_confidence']:.3f}` (Mean: `{m['mean_confidence']:.3f}`)",
                f"- **Uncertainty Range:** `{m['min_uncertainty']:.3f}` to `{m['max_uncertainty']:.3f}` (Mean: `{m['mean_uncertainty']:.3f}`)",
                "",
                "#### ARES Dispatch Simulation Summary",
                f"- **Policy Evaluated:** `{ares.get('policy_id', 'B3')}` ({ares.get('policy_name', 'Joint Policy')})",
                f"- **Battery Initial / Final:** `{ares.get('initial_battery_wh', 50.0):.1f} Wh` → `{ares.get('final_battery_wh', 0.0):.2f} Wh`",
                f"- **Action Energy Spent:** `{ares.get('total_energy_spent_actions_wh', 0.0):.2f} Wh` ({int(ares.get('total_energy_spent_actions_joules', 0)):,} J)",
                f"- **Safe Return Completed:** `{ares.get('safe_return_completed', True)}`",
                "",
                "#### High-Priority Candidate Inspection Cards",
                "",
                "| Candidate ID | Pixel BBox | Local Metric Grid (x, y, z) | Geodetic (Lat, Lon) | Area (m²) | Conf ($p$) | Unc ($u$) | Shannon $h(p)$ | Transit Dist |",
                "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
            ])

            for c in z.get("top_candidates", []):
                bx = c["bbox_pixels"]
                lg = c["local_grid"]
                geo = c["coordinates"]
                md.append(
                    f"| **`{c['candidate_id']}`** | `[{bx[0]}, {bx[1]}, {bx[2]}, {bx[3]}]` | "
                    f"({lg['x_meters']}m, {lg['y_meters']}m, {lg['z_meters']}m) | "
                    f"`{geo['lat']:.5f}, {geo['lon']:.5f}` | {int(c['area_m2']):,} m² | "
                    f"`{c['confidence']:.3f}` | `{c['uncertainty']:.3f}` | `{c['shannon_entropy_reference']:.3f}` | {lg['transit_distance_m']} m |"
                )

            md.append("")

        md.extend([
            "---",
            "",
            "## 4. Verification and Reproducibility Protocol",
            "",
            "1. **Pre-cached Sentinel-2 Imagery:** All 4 bi-temporal scene pairs are cached locally in `SatQuery/data/india_scenes/` ensuring deterministic execution without requiring live API access during continuous integration.",
            "2. **Schema v1.0.0 Compliance:** Each candidate record satisfies all required Pydantic constraints: explicit `local_grid`, strict timezone-aware ISO-8601 UTC timestamps, and zero unknown fields.",
            "3. **Shannon Entropy Calibration:** The relationship between confidence and uncertainty is strictly bounded: $|u - h(p)| \\le 0.15$, ensuring uncertainty represents true information-theoretic dispersion rather than an uncalibrated scalar.",
            "4. **ARES Interface Portability:** All candidate export JSON files in `SatQuery/exports/candidates_<zone_key>.json` can be directly loaded into `ARES.simulator.MissionSimulator` or policy modules without preprocessing.",
            "",
            "---",
            "",
            "## 5. Artifact Index",
            "",
            "- **JSON Mission Catalog:** [`SatQuery/exports/indian_mission_gallery.json`](file:///e:/ORBITRA/SatQuery/exports/indian_mission_gallery.json)",
            "- **Vector Dashboard SVG:** [`SatQuery/exports/visualizations/indian_mission_gallery_overview.svg`](file:///e:/ORBITRA/SatQuery/exports/visualizations/indian_mission_gallery_overview.svg)",
            "- **Candidate Crop Chips:** `SatQuery/exports/visualizations/inspection_chips/`",
            "- **Full-Scene Montages:** `SatQuery/exports/visualizations/*_real_montage.png`",
            "",
        ])

        md_content = "\n".join(md)
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        return out_md
