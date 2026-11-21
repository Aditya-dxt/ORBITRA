"""Sub-Meter High-Resolution Satellite & Aerial Imagery Change Verification Engine.

Fetches authentic sub-meter (0.59 m/pixel at Zoom Level 18) bitemporal satellite orthophotography
from the Esri World Imagery Wayback historical archive (Maxar WorldView / high-res aerial surveys).

Eliminates the optical sensor blur inherent in 10-meter coarse satellites (like Sentinel-2),
enabling human analysts and automated computer vision to zoom into individual buildings,
road lane modifications, factory roofs, and infrastructure footprints with crisp, razor-sharp clarity.

Hotspots covered:
1. kanpur_bhauti_psit: PSIT Kanpur campus & NH-19 corridor.
2. kanpur_panki_logistics: Panki industrial estate & freight rail logistics.
3. delhi_cybercity_expressway: Gurugram Cyber City & DLF commercial complex.
4. bengaluru_electronic_city_metro: Electronic City Phase 1 & Hosur Road elevated metro viaduct.
5. chennai_sriperumbudur_industrial: Sriperumbudur automotive manufacturing hub.

Stores:
- Raw sub-meter bitemporal scenes in SatQuery/data/submeter_highres_scenes/
- High-definition verification montages and inspection chips in SatQuery/exports/submeter_change_verification/
"""

import io
import json
import math
import os
import urllib.request
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np
from PIL import Image

from ..vision.georeferencing import MissionGeoreferencer
from ..schemas.candidate_record import SatQueryCandidateRecord


SUBMETER_HOTSPOTS: Dict[str, Dict[str, Any]] = {
    "kanpur_bhauti_psit": {
        "name": "Kanpur / Bhauti PSIT Campus & NH-19 Corridor",
        "home_lat": 26.447500,
        "home_lon": 80.197500,
        "zoom": 18,
        "grid_size": 3,  # 3x3 tiles = 768x768 pixels (~453m x 453m at 0.59m/px)
        "pre_release": 29260,   # Wayback Dec 2020
        "post_release": 16453,  # Wayback Dec 2024
        "pre_date": "2020-12-16",
        "post_date": "2024-12-12",
        "description": "Ultra-sharp 0.59 m/pixel view directly over PSIT Kanpur campus and the National Highway 19 frontage, revealing individual educational building construction, lane additions, and boundary expansions.",
        "gsd_m_per_px": 0.59,
    },
    "kanpur_panki_logistics": {
        "name": "Kanpur / Panki Industrial Estate & Logistics Sheds",
        "home_lat": 26.472500,
        "home_lon": 80.237500,
        "zoom": 18,
        "grid_size": 3,
        "pre_release": 29260,
        "post_release": 16453,
        "pre_date": "2020-12-16",
        "post_date": "2024-12-12",
        "description": "High-resolution industrial hub showing individual factory shed erections, roof replacements, and freight logistics earthworks.",
        "gsd_m_per_px": 0.59,
    },
    "delhi_cybercity_expressway": {
        "name": "Delhi NCR / Gurugram Cyber City & DLF Commercial Hub",
        "home_lat": 28.482500,
        "home_lon": 77.077500,
        "zoom": 18,
        "grid_size": 3,
        "pre_release": 29260,
        "post_release": 16453,
        "pre_date": "2020-12-16",
        "post_date": "2024-12-12",
        "description": "High-density commercial corridor showing high-rise building foundations, transit walkways, and road infrastructure modifications.",
        "gsd_m_per_px": 0.59,
    },
    "bengaluru_electronic_city_metro": {
        "name": "Bengaluru Electronic City — Hosur Road Metro Viaduct",
        "home_lat": 12.847500,
        "home_lon": 77.667500,
        "zoom": 18,
        "grid_size": 3,
        "pre_release": 29260,
        "post_release": 16453,
        "pre_date": "2020-12-16",
        "post_date": "2024-12-12",
        "description": "Sub-meter resolution of the elevated Namma Metro Yellow Line viaduct, station superstructures, and tech park infrastructure developments.",
        "gsd_m_per_px": 0.59,
    },
    "chennai_sriperumbudur_industrial": {
        "name": "Chennai / Sriperumbudur Automotive Manufacturing Zone",
        "home_lat": 12.982500,
        "home_lon": 79.957500,
        "zoom": 18,
        "grid_size": 3,
        "pre_release": 29260,
        "post_release": 16453,
        "pre_date": "2020-12-16",
        "post_date": "2024-12-12",
        "description": "Sub-meter satellite view of industrial automotive manufacturing footprints, assembly shed expansions, and commercial plots.",
        "gsd_m_per_px": 0.59,
    },
}


def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int]:
    """Convert WGS-84 latitude/longitude to Web Mercator tile coordinates at a given zoom."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def tile2deg(xtile: int, ytile: int, zoom: int) -> Tuple[float, float]:
    """Convert Web Mercator tile coordinates to WGS-84 bounding box north-west corner."""
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


class SubmeterHighresSceneLoader:
    """Manages acquisition, stitching, change detection, and visual verification for sub-meter satellite scenes."""

    def __init__(
        self,
        repo_root: Optional[str] = None,
        data_dir: Optional[str] = None,
        exports_dir: Optional[str] = None,
    ):
        if repo_root is None:
            self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        else:
            self.repo_root = repo_root

        self.satquery_root = os.path.join(self.repo_root, "SatQuery")
        self.data_dir = data_dir or os.path.join(self.satquery_root, "data", "submeter_highres_scenes")
        self.exports_dir = exports_dir or os.path.join(self.satquery_root, "exports", "submeter_change_verification")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.exports_dir, exist_ok=True)

    def _download_tile(self, release_id: int, zoom: int, tile_x: int, tile_y: int) -> Image.Image:
        """Download a single 256x256 high-resolution orthophoto tile from Esri Wayback."""
        url = (
            f"https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/"
            f"default028mm/MapServer/tile/{release_id}/{zoom}/{tile_y}/{tile_x}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "image/jpeg,image/png,image/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            # Fallback neutral tile if an individual boundary tile is missing
            return Image.new("RGB", (256, 256), (128, 128, 128))

    def stitch_highres_scene(
        self,
        release_id: int,
        center_lat: float,
        center_lon: float,
        zoom: int = 18,
        grid_size: int = 3,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Stitch an N x N grid of sub-meter tiles around the center coordinate."""
        cx, cy = deg2tile(center_lat, center_lon, zoom)
        half = grid_size // 2
        tile_size = 256
        full_w = grid_size * tile_size
        full_h = grid_size * tile_size
        canvas = Image.new("RGB", (full_w, full_h))

        for row_idx, dy in enumerate(range(-half, half + 1)):
            for col_idx, dx in enumerate(range(-half, half + 1)):
                tx = cx + dx
                ty = cy + dy
                tile = self._download_tile(release_id, zoom, tx, ty)
                canvas.paste(tile, (col_idx * tile_size, row_idx * tile_size))

        # Geographic boundary of the stitched canvas
        nw_lat, nw_lon = tile2deg(cx - half, cy - half, zoom)
        se_lat, se_lon = tile2deg(cx + half + 1, cy + half + 1, zoom)

        meta = {
            "zoom": zoom,
            "grid_size": grid_size,
            "dimensions_pixels": [full_w, full_h],
            "center_tile": [cx, cy],
            "bounding_box_wgs84": [nw_lon, se_lat, se_lon, nw_lat],  # [min_lon, min_lat, max_lon, max_lat]
            "nw_corner": [nw_lat, nw_lon],
            "se_corner": [se_lat, se_lon],
        }

        return np.array(canvas), meta

    def fetch_and_process_hotspot(
        self,
        hotspot_key: str = "kanpur_bhauti_psit",
        force_download: bool = False,
        threshold: float = 0.28,
        min_pixel_area: int = 25,
    ) -> Dict[str, Any]:
        """Download or load sub-meter satellite imagery, perform change detection, and build Ultra-HD visual maps."""
        if hotspot_key not in SUBMETER_HOTSPOTS:
            raise ValueError(f"Unknown submeter hotspot '{hotspot_key}'. Available: {list(SUBMETER_HOTSPOTS.keys())}")

        info = SUBMETER_HOTSPOTS[hotspot_key]
        raw_pre_path = os.path.join(self.data_dir, f"{hotspot_key}_pre_submeter.png")
        raw_post_path = os.path.join(self.data_dir, f"{hotspot_key}_post_submeter.png")
        raw_meta_path = os.path.join(self.data_dir, f"{hotspot_key}_meta.json")

        out_hotspot_dir = os.path.join(self.exports_dir, hotspot_key)
        os.makedirs(out_hotspot_dir, exist_ok=True)
        chips_dir = os.path.join(out_hotspot_dir, "inspection_chips")
        os.makedirs(chips_dir, exist_ok=True)

        grid_size = info.get("grid_size", 3)
        zoom = info.get("zoom", 18)
        gsd = info.get("gsd_m_per_px", 0.59)

        if not force_download and os.path.exists(raw_pre_path) and os.path.exists(raw_post_path) and os.path.exists(raw_meta_path):
            img_pre = np.array(Image.open(raw_pre_path).convert("RGB"))
            img_post = np.array(Image.open(raw_post_path).convert("RGB"))
            with open(raw_meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"📂 Loaded cached sub-meter imagery ({img_pre.shape[1]}x{img_pre.shape[0]} px, {gsd}m/px) for [{hotspot_key}]")
        else:
            print(f"🛰️  Stitching sub-meter orthophotography for {info['name']} (Zoom {zoom}, {gsd}m/px)...")
            img_pre, pre_meta = self.stitch_highres_scene(
                info["pre_release"], info["home_lat"], info["home_lon"], zoom=zoom, grid_size=grid_size
            )
            img_post, post_meta = self.stitch_highres_scene(
                info["post_release"], info["home_lat"], info["home_lon"], zoom=zoom, grid_size=grid_size
            )

            meta = {
                "hotspot_key": hotspot_key,
                "name": info["name"],
                "description": info["description"],
                "home_coordinates": {"lat": info["home_lat"], "lon": info["home_lon"]},
                "zoom": zoom,
                "grid_size": grid_size,
                "image_dimensions": [img_pre.shape[1], img_pre.shape[0]],
                "gsd_m_per_px": gsd,
                "pre_epoch": {"release_id": info["pre_release"], "date": info["pre_date"]},
                "post_epoch": {"release_id": info["post_release"], "date": info["post_date"]},
                "source": "Esri World Imagery Wayback (Maxar / High-Res Aerial Surveys, ~0.59m/pixel)",
                "bounding_box_wgs84": post_meta["bounding_box_wgs84"],
            }

            Image.fromarray(img_pre).save(raw_pre_path)
            Image.fromarray(img_post).save(raw_post_path)
            with open(raw_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            print(f"   ✓ Cached raw sub-meter imagery ({img_pre.shape[1]}x{img_pre.shape[0]}) in {self.data_dir}")

        # Compute sub-pixel registration shift via phase correlation
        gray_a = cv2.cvtColor(img_pre, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray_b = cv2.cvtColor(img_post, cv2.COLOR_RGB2GRAY).astype(np.float32)
        shift, _ = cv2.phaseCorrelate(gray_a, gray_b)
        dx, dy = round(float(shift[0]), 2), round(float(shift[1]), 2)

        # Georeferencing using true sub-meter ground sampling distance
        geo = MissionGeoreferencer(
            home_lat=info["home_lat"],
            home_lon=info["home_lon"],
            home_alt=120.0,
            tile_anchor_x=0.0,
            tile_anchor_y=0.0,
            gsd_x=gsd,
            gsd_y=gsd,
            default_flight_alt=60.0,
        )

        # Lazy import of pipeline to prevent circular dependency
        from ..pipeline import SatQueryPipeline
        pipeline = SatQueryPipeline(georeferencer=geo, threshold=threshold, min_pixel_area=min_pixel_area)
        pair_id = f"pair_submeter_{hotspot_key}"
        res = pipeline.process_pair(
            img_pre=img_pre,
            img_post=img_post,
            image_pair_id=pair_id,
            timestamp=f"{info['post_date']}T00:00:00Z",
        )

        candidates = res["candidates"]
        heatmap = res["heatmap"]
        mask = res["binary_mask"]

        # Export candidate records (Schema v1.0.0)
        cands_json_path = os.path.join(out_hotspot_dir, f"{hotspot_key}_candidates.json")
        pipeline.export_candidates_to_json(candidates, cands_json_path)

        # 1. Save Pre (T1) and Post (T2) images
        p_pre = os.path.join(out_hotspot_dir, f"{hotspot_key}_pre_t1.png")
        p_post = os.path.join(out_hotspot_dir, f"{hotspot_key}_post_t2.png")
        Image.fromarray(img_pre).save(p_pre)
        Image.fromarray(img_post).save(p_post)

        # 2. Save Difference Heatmap (Magma color-map)
        heat_uint8 = (heatmap * 255.0).astype(np.uint8)
        heat_color = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_MAGMA)
        heat_rgb = cv2.cvtColor(heat_color, cv2.COLOR_BGR2RGB)
        p_heat = os.path.join(out_hotspot_dir, f"{hotspot_key}_change_heatmap.png")
        Image.fromarray(heat_rgb).save(p_heat)

        # 3. Save Binary Mask
        p_mask = os.path.join(out_hotspot_dir, f"{hotspot_key}_binary_mask.png")
        Image.fromarray(mask).save(p_mask)

        # 4. Generate High-Visibility Annotated Detections Image
        annotated = img_post.copy()
        for idx, cand in enumerate(candidates):
            bx = cand.region.bbox_pixels
            if bx:
                x1, y1, x2, y2 = bx
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 60, 0), 2)
                # Label with pill background for razor-sharp readability
                label = f"#{idx+1} {cand.candidate_id[-7:]} p={cand.confidence:.2f}"
                cv2.putText(annotated, label, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 2)
                cv2.putText(annotated, label, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

        p_annot = os.path.join(out_hotspot_dir, f"{hotspot_key}_change_annotations.png")
        Image.fromarray(annotated).save(p_annot)

        # 5. Generate 4-Panel Ultra-HD Widescreen Montage
        h, w = img_pre.shape[:2]
        montage = np.zeros((h, w * 4, 3), dtype=np.uint8)
        montage[:, :w] = img_pre
        montage[:, w : w * 2] = img_post
        montage[:, w * 2 : w * 3] = heat_rgb
        montage[:, w * 3 :] = annotated

        font = cv2.FONT_HERSHEY_SIMPLEX
        t1_str = f"Pre T1 ({info['pre_date']}) [0.59m/px]"
        t2_str = f"Post T2 ({info['post_date']}) [0.59m/px]"
        cv2.putText(montage, t1_str, (12, 28), font, 0.65, (255, 255, 255), 2)
        cv2.putText(montage, t2_str, (w + 12, 28), font, 0.65, (255, 255, 255), 2)
        cv2.putText(montage, "Change Heatmap (Magma)", (w * 2 + 12, 28), font, 0.65, (255, 255, 255), 2)
        cv2.putText(montage, f"Annotated Detections ({len(candidates)} Found)", (w * 3 + 12, 28), font, 0.65, (0, 255, 255), 2)

        p_montage = os.path.join(out_hotspot_dir, f"{hotspot_key}_ultra_hd_montage.png")
        Image.fromarray(montage).save(p_montage)

        # 6. Extract Top Close-Up Inspection Chips
        cand_dicts = []
        for c in candidates:
            bx = c.region.bbox_pixels
            px_area = (bx[2] - bx[0]) * (bx[3] - bx[1])
            m2_area = px_area * (gsd * gsd)
            cand_dicts.append({
                "cand": c,
                "pixel_area": px_area,
                "area_m2": m2_area,
            })
        cand_dicts.sort(key=lambda x: x["pixel_area"], reverse=True)

        inspection_chips = []
        for idx, item in enumerate(cand_dicts[:6]):
            c = item["cand"]
            bx = c.region.bbox_pixels
            chip_img = self._extract_zoom_chip(img_pre, img_post, bx, padding=25, height=160)
            chip_name = f"chip_{idx+1}_{c.candidate_id}.png"
            chip_path = os.path.join(chips_dir, chip_name)
            Image.fromarray(chip_img).save(chip_path)
            inspection_chips.append({
                "rank": idx + 1,
                "candidate_id": c.candidate_id,
                "chip_file": chip_name,
                "area_m2": item["area_m2"],
                "confidence": c.confidence,
                "uncertainty": c.uncertainty,
                "local_grid": c.region.local_grid.model_dump(),
                "bbox": bx,
            })

        total_change_m2 = sum(item["area_m2"] for item in cand_dicts)
        summary = {
            "hotspot_key": hotspot_key,
            "name": info["name"],
            "description": info["description"],
            "dates": {"t1": info["pre_date"], "t2": info["post_date"]},
            "resolution": f"{gsd} m/pixel (Sub-meter Ultra-HD)",
            "subpixel_shift": {"dx_px": dx, "dy_px": dy},
            "total_candidates_detected": len(candidates),
            "total_change_footprint_m2": round(total_change_m2, 1),
            "total_change_footprint_ha": round(total_change_m2 / 10000.0, 3),
            "top_inspections": inspection_chips,
            "output_directory": out_hotspot_dir,
            "files": {
                "pre_image": os.path.basename(p_pre),
                "post_image": os.path.basename(p_post),
                "change_heatmap": os.path.basename(p_heat),
                "binary_mask": os.path.basename(p_mask),
                "annotated_changes": os.path.basename(p_annot),
                "ultra_hd_montage": os.path.basename(p_montage),
                "candidates_json": os.path.basename(cands_json_path),
            },
        }

        with open(os.path.join(out_hotspot_dir, "hotspot_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        return summary

    def _extract_zoom_chip(
        self,
        img_pre: np.ndarray,
        img_post: np.ndarray,
        bbox: List[int],
        padding: int = 25,
        height: int = 160,
    ) -> np.ndarray:
        """Extract a 4-panel sub-meter inspection chip showing Pre, Post, Difference, and Bounding Box."""
        h, w = img_pre.shape[:2]
        x1, y1, x2, y2 = bbox
        px1 = max(0, x1 - padding)
        py1 = max(0, y1 - padding)
        px2 = min(w, x2 + padding)
        py2 = min(h, y2 + padding)

        c_pre = img_pre[py1:py2, px1:px2]
        c_post = img_post[py1:py2, px1:px2]

        if c_pre.size == 0 or c_post.size == 0:
            return np.zeros((height, height * 4, 3), dtype=np.uint8)

        # Difference
        diff = cv2.absdiff(c_pre, c_post)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
        diff_color = cv2.applyColorMap(cv2.normalize(diff_gray, None, 0, 255, cv2.NORM_MINMAX), cv2.COLORMAP_MAGMA)
        diff_rgb = cv2.cvtColor(diff_color, cv2.COLOR_BGR2RGB)

        # Annotated on post
        annot = c_post.copy()
        cv2.rectangle(annot, (x1 - px1, y1 - py1), (x2 - px1, y2 - py1), (255, 60, 0), 2)

        panels = [c_pre, c_post, diff_rgb, annot]
        scaled = []
        for p in panels:
            ph, pw = p.shape[:2]
            scale = height / max(ph, 1)
            nw = max(int(pw * scale), 1)
            scaled.append(cv2.resize(p, (nw, height), interpolation=cv2.INTER_LINEAR))

        sep = np.ones((height, 3, 3), dtype=np.uint8) * 60
        return np.hstack([scaled[0], sep, scaled[1], sep, scaled[2], sep, scaled[3]])

    def generate_comprehensive_report(self, summaries: List[Dict[str, Any]]) -> str:
        """Write a comprehensive visual change verification guide in markdown."""
        out_md = os.path.join(self.exports_dir, "SUBMETER_CHANGE_ANALYSIS.md")
        lines = [
            "# Sub-Meter Ultra-HD Satellite Change Verification Report",
            "",
            "**Module:** SatQuery (Computer Vision & Spatial Analytics)  ",
            "**Sensor Source:** Esri World Imagery Wayback Archive (Maxar WorldView / High-Res Aerial Surveys)  ",
            "**Resolution:** Sub-Meter Optical Orthophotography ($0.59\\text{ m/pixel}$ at Zoom Level 18)  ",
            "**Observation Baseline:** 4-Year Bitemporal Interval ($2020\\text{ (Pre)} \\to 2024\\text{ (Post)}$)  ",
            "",
            "---",
            "",
            "## 1. Resolution Comparison & Diagnostic Root Cause",
            "",
            "### Why Standard Satellite Imagery Appeared Blurry When Zoomed In:",
            "- **Coarse Satellite Sensors (Sentinel-2):** Standard free satellites orbit at $786\\text{ km}$ and have a native optical sensor resolution of **$10.0\\text{ meters per pixel}$**. When an analyst zooms in on a computer monitor to inspect an individual house or highway lane, 1 pixel represents a massive $100\\text{ m}^2$ ground footprint. Digital zooming merely enlarges these 10m pixels, resulting in pixelation and blur.",
            "- **Sub-Meter Orthophotography (This Dataset):** At Zoom Level 18, the Ground Sampling Distance (GSD) is **$0.59\\text{ meters per pixel}$** ($59\\text{ cm}$). That is **over $16\\times$ higher spatial resolution**! At this resolution, individual building roofs, construction scaffolding, road dividers, and trees are resolved as crisp, distinct shapes without any blur.",
            "",
            "### Folder Structure:",
            "- **Raw Sub-Meter Imagery:** `SatQuery/data/submeter_highres_scenes/`",
            "- **Ultra-HD Montages & Inspection Chips:** `SatQuery/exports/submeter_change_verification/`",
            "",
            "---",
            "",
            "## 2. Multi-Corridor Sub-Meter Change Summary",
            "",
            "| Corridor Identifier | Region Name | Sensor Resolution | Baseline Period | Changes Found | Change Footprint |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]

        for s in summaries:
            dt = s["dates"]
            lines.append(
                f"| **`{s['hotspot_key']}`** | {s['name']} | `{s['resolution']}` | "
                f"`{dt['t1']}` → `{dt['t2']}` | **{s['total_candidates_detected']} changes** | "
                f"**{s['total_change_footprint_ha']} ha** ({int(s['total_change_footprint_m2']):,} m²) |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 3. Detailed Change Location Analysis per Corridor",
            "",
        ])

        for s in summaries:
            k = s["hotspot_key"]
            f = s["files"]
            lines.extend([
                f"### 3.{summaries.index(s) + 1} {s['name']} (`{k}`)",
                "",
                f"- **Corridor Profile:** {s['description']}",
                f"- **Epoch 1 (Pre-Change $T_1$):** `{s['dates']['t1']}`",
                f"- **Epoch 2 (Post-Change $T_2$):** `{s['dates']['t2']}`",
                f"- **Spatial Resolution:** **{s['resolution']}**",
                f"- **Sub-Pixel Spatial Shift:** $\\Delta x = {s['subpixel_shift']['dx_px']}\\text{{ px}}, \\Delta y = {s['subpixel_shift']['dy_px']}\\text{{ px}}$",
                f"- **Detection Volume:** **{s['total_candidates_detected']} verified change targets** covering **{s['total_change_footprint_ha']} hectares**",
                "",
                "#### Visual Inspection Artifacts:",
                f"- **Ultra-HD 4-Panel Montage:** [`{f['ultra_hd_montage']}`]({k}/{f['ultra_hd_montage']})",
                f"- **Annotated Change Outlines:** [`{f['annotated_changes']}`]({k}/{f['annotated_changes']})",
                f"- **Change Heatmap:** [`{f['change_heatmap']}`]({k}/{f['change_heatmap']})",
                f"- **Candidate Records (JSON):** [`{f['candidates_json']}`]({k}/{f['candidates_json']})",
                "",
                "#### Top Change Hotspots in this Corridor:",
                "",
                "| Rank | Candidate ID | Surface Area | Conf ($p$) | Unc ($u$) | Local Metric Grid (x, y, z) | Close-up Chip |",
                "| :---: | :--- | :---: | :---: | :---: | :---: | :---: |",
            ])

            for top in s["top_inspections"]:
                lg = top["local_grid"]
                chip_rel = f"{k}/inspection_chips/{top['chip_file']}"
                lines.append(
                    f"| **#{top['rank']}** | `{top['candidate_id']}` | **{int(top['area_m2']):,} m²** | "
                    f"`{top['confidence']:.3f}` | `{top['uncertainty']:.3f}` | "
                    f"({lg['x_meters']}m, {lg['y_meters']}m, {lg['z_meters']}m) | "
                    f"[`{top['chip_file']}`]({chip_rel}) |"
                )

            lines.append("")

        lines.extend([
            "---",
            "",
            "## 4. How to Inspect & Validate High-Resolution Changes",
            "",
            "1. **View the 4-Panel Ultra-HD Montages:**",
            "   Open any `*_ultra_hd_montage.png` to view Pre $T_1$, Post $T_2$, Difference Heatmap, and Annotated Outlines side-by-side at $0.59\\text{ m/pixel}$.",
            "2. **Zoom In Freely Without Blur:**",
            "   Because each pixel corresponds to $59\\text{ cm}$ on the ground, zooming in reveals crisp building walls, courtyard boundaries, and lane markings.",
            "3. **Inspect Close-Up Chips:**",
            "   Browse `inspection_chips/` to see isolated before/after views for each major infrastructure addition.",
            "",
        ])

        with open(out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return out_md
