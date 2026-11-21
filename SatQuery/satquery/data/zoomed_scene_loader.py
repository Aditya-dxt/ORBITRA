"""Zoomed Real Satellite Imagery Loader & Change Verification Engine.

Downloads, caches, and processes high-resolution zoomed bitemporal Sentinel-2 Level-2A imagery
over targeted geographic hotspots, providing clear localized visual change identification:
1. kanpur_bhauti_nh19: Tightly zoomed NH-19 highway corridor & industrial warehousing near PSIT Kanpur.
2. kanpur_panki_industrial: Panki industrial estate, logistics yards, and commercial expansions.
3. delhi_gurugram_cybercity: Gurugram Cyber City & Sector 29 commercial construction corridor.
4. bengaluru_electronic_city: Electronic City Hosur Road & Namma Metro Yellow Line viaduct development.
5. chennai_sriperumbudur: Sriperumbudur manufacturing hub and automotive plant development.

Stores:
- Raw downloaded bitemporal satellite imagery in SatQuery/data/zoomed_real_scenes/
- Annotated visual change maps, side-by-side montages, inspection chips, and reports in
  SatQuery/exports/zoomed_change_verification/
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


ZOOMED_MISSION_HOTSPOTS: Dict[str, Dict[str, Any]] = {
    "kanpur_bhauti_nh19": {
        "name": "Kanpur / Bhauti PSIT Corridor (NH-19 Highway Widening)",
        "home_lat": 26.447500,
        "home_lon": 80.197500,
        "bbox": [80.180, 26.435, 80.215, 26.460],
        "pre_date_range": "2021-11-01T00:00:00Z/2021-12-31T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2023-12-31T00:00:00Z",
        "description": "High-resolution 3.5 km corridor along National Highway 19 directly in front of PSIT Kanpur, highlighting new industrial warehousing, highway lane expansion, and institutional construction.",
        "gsd_m_per_px": 5.0,
    },
    "kanpur_panki_industrial": {
        "name": "Kanpur / Panki Industrial Estate & Logistics Hub",
        "home_lat": 26.472500,
        "home_lon": 80.237500,
        "bbox": [80.220, 26.460, 80.255, 26.485],
        "pre_date_range": "2021-11-01T00:00:00Z/2021-12-31T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2023-12-31T00:00:00Z",
        "description": "Zoomed industrial zone showing factory shed construction, rail spur logistics, and commercial ground modifications.",
        "gsd_m_per_px": 5.0,
    },
    "delhi_gurugram_cybercity": {
        "name": "Delhi NCR / Gurugram Development Corridor (Cyber City & Sector 29)",
        "home_lat": 28.482500,
        "home_lon": 77.077500,
        "bbox": [77.060, 28.470, 77.095, 28.495],
        "pre_date_range": "2021-10-01T00:00:00Z/2021-12-31T00:00:00Z",
        "post_date_range": "2023-10-01T00:00:00Z/2023-12-31T00:00:00Z",
        "description": "Zoomed high-density commercial construction along the Gurugram expressway and mixed-use commercial developments.",
        "gsd_m_per_px": 5.0,
    },
    "bengaluru_electronic_city": {
        "name": "Bengaluru Electronic City — Namma Metro Yellow Line Viaduct",
        "home_lat": 12.847500,
        "home_lon": 77.667500,
        "bbox": [77.650, 12.835, 77.685, 12.860],
        "pre_date_range": "2021-11-01T00:00:00Z/2022-01-31T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2024-01-31T00:00:00Z",
        "description": "Zoomed transit infrastructure corridor along Hosur Road showing viaduct construction and tech park infrastructure developments.",
        "gsd_m_per_px": 5.0,
    },
    "chennai_sriperumbudur": {
        "name": "Chennai / Sriperumbudur Automotive Manufacturing Zone",
        "home_lat": 12.982500,
        "home_lon": 79.957500,
        "bbox": [79.940, 12.970, 79.975, 12.995],
        "pre_date_range": "2021-11-01T00:00:00Z/2022-02-28T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2024-02-28T00:00:00Z",
        "description": "Zoomed manufacturing corridor showing industrial building footprints and automotive manufacturing expansions.",
        "gsd_m_per_px": 5.0,
    },
}


class ZoomedSceneLoader:
    """Manages acquisition, caching, change detection, and visual verification for zoomed satellite scenes."""

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
        self.data_dir = data_dir or os.path.join(self.satquery_root, "data", "zoomed_real_scenes")
        self.exports_dir = exports_dir or os.path.join(self.satquery_root, "exports", "zoomed_change_verification")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.exports_dir, exist_ok=True)

        self._sas_token: Optional[str] = None

    def _get_planetary_sas_token(self) -> str:
        """Fetch read SAS token from Microsoft Planetary Computer."""
        if self._sas_token is not None:
            return self._sas_token
        url = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
        req = urllib.request.Request(url, headers={"User-Agent": "ORBITRA-SatQuery/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self._sas_token = data.get("token", "")
        return self._sas_token

    def _query_stac_scene(self, bbox: List[float], datetime_range: str) -> Tuple[str, str, str]:
        """Search Planetary Computer STAC for lowest cloud cover Sentinel-2 L2A scene."""
        url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
        payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": bbox,
            "datetime": datetime_range,
            "query": {"eo:cloud_cover": {"lt": 10}},
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            "limit": 1,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "ORBITRA-SatQuery/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            features = data.get("features", [])
            if not features:
                raise ValueError(f"No Sentinel-2 imagery found for bbox {bbox} in {datetime_range}")
            item = features[0]
            scene_id = item["id"]
            obs_dt = item["properties"]["datetime"]
            return scene_id, obs_dt

    def _download_bbox_image(
        self,
        item_id: str,
        bbox: List[float],
        width: int = 512,
        height: int = 512,
    ) -> np.ndarray:
        """Download high-resolution zoomed satellite imagery covering the exact bounding box."""
        token = self._get_planetary_sas_token()
        bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        url = (
            f"https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/{bbox_str}.png"
            f"?collection=sentinel-2-l2a&item={item_id}&assets=visual"
            f"&width={width}&height={height}&nodata=0&{token}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ORBITRA-SatQuery/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_bytes = resp.read()
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return np.array(pil_img)

    def fetch_and_process_hotspot(
        self,
        hotspot_key: str = "kanpur_bhauti_nh19",
        image_size: int = 512,
        force_download: bool = False,
        threshold: float = 0.32,
        min_pixel_area: int = 15,
    ) -> Dict[str, Any]:
        """Download or load zoomed real satellite imagery, detect changes, and generate visual inspection maps."""
        if hotspot_key not in ZOOMED_MISSION_HOTSPOTS:
            raise ValueError(f"Unknown hotspot '{hotspot_key}'. Available: {list(ZOOMED_MISSION_HOTSPOTS.keys())}")

        info = ZOOMED_MISSION_HOTSPOTS[hotspot_key]
        raw_pre_path = os.path.join(self.data_dir, f"{hotspot_key}_pre_real.png")
        raw_post_path = os.path.join(self.data_dir, f"{hotspot_key}_post_real.png")
        raw_meta_path = os.path.join(self.data_dir, f"{hotspot_key}_meta.json")

        out_hotspot_dir = os.path.join(self.exports_dir, hotspot_key)
        os.makedirs(out_hotspot_dir, exist_ok=True)
        chips_dir = os.path.join(out_hotspot_dir, "inspection_chips")
        os.makedirs(chips_dir, exist_ok=True)

        if not force_download and os.path.exists(raw_pre_path) and os.path.exists(raw_post_path) and os.path.exists(raw_meta_path):
            img_pre = np.array(Image.open(raw_pre_path).convert("RGB"))
            img_post = np.array(Image.open(raw_post_path).convert("RGB"))
            with open(raw_meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"📂 Loaded cached zoomed satellite imagery for [{hotspot_key}] from {self.data_dir}")
        else:
            print(f"🛰️  Acquiring zoomed real Sentinel-2 satellite imagery for {info['name']}...")
            id_pre, dt_pre = self._query_stac_scene(info["bbox"], info["pre_date_range"])
            id_post, dt_post = self._query_stac_scene(info["bbox"], info["post_date_range"])

            img_pre = self._download_bbox_image(id_pre, info["bbox"], width=image_size, height=image_size)
            img_post = self._download_bbox_image(id_post, info["bbox"], width=image_size, height=image_size)

            meta = {
                "hotspot_key": hotspot_key,
                "name": info["name"],
                "description": info["description"],
                "home_coordinates": {"lat": info["home_lat"], "lon": info["home_lon"]},
                "bounding_box_wgs84": info["bbox"],
                "pre_scene_id": id_pre,
                "pre_datetime": dt_pre,
                "post_scene_id": id_post,
                "post_datetime": dt_post,
                "image_dimensions": [image_size, image_size],
                "source": "ESA Sentinel-2 Level-2A (Optical Surface Reflectance)",
                "gsd_m_per_px": info.get("gsd_m_per_px", 5.0),
            }

            Image.fromarray(img_pre).save(raw_pre_path)
            Image.fromarray(img_post).save(raw_post_path)
            with open(raw_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            print(f"   ✓ Cached raw zoomed imagery ({image_size}x{image_size}) in {self.data_dir}")

        # Compute sub-pixel registration shift
        gray_a = cv2.cvtColor(img_pre, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray_b = cv2.cvtColor(img_post, cv2.COLOR_RGB2GRAY).astype(np.float32)
        shift, _ = cv2.phaseCorrelate(gray_a, gray_b)
        dx, dy = round(float(shift[0]), 2), round(float(shift[1]), 2)

        # Configure Georeferencing
        gsd = info.get("gsd_m_per_px", 5.0)
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

        # Run Change Detection Pipeline
        from ..pipeline import SatQueryPipeline
        pipeline = SatQueryPipeline(georeferencer=geo, threshold=threshold, min_pixel_area=min_pixel_area)
        pair_id = f"pair_zoomed_{hotspot_key}"
        res = pipeline.process_pair(
            img_pre=img_pre,
            img_post=img_post,
            image_pair_id=pair_id,
            timestamp=meta.get("post_datetime", "2023-12-01T00:00:00Z"),
        )

        candidates = res["candidates"]
        heatmap = res["heatmap"]
        mask = res["binary_mask"]

        # Export candidate records (Schema v1.0.0)
        cands_json_path = os.path.join(out_hotspot_dir, f"{hotspot_key}_candidates.json")
        pipeline.export_candidates_to_json(candidates, cands_json_path)

        # 1. Save Pre and Post T1/T2
        p_pre = os.path.join(out_hotspot_dir, f"{hotspot_key}_pre_t1.png")
        p_post = os.path.join(out_hotspot_dir, f"{hotspot_key}_post_t2.png")
        Image.fromarray(img_pre).save(p_pre)
        Image.fromarray(img_post).save(p_post)

        # 2. Save Difference Heatmap
        heat_uint8 = (heatmap * 255.0).astype(np.uint8)
        heat_color = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_MAGMA)
        heat_rgb = cv2.cvtColor(heat_color, cv2.COLOR_BGR2RGB)
        p_heat = os.path.join(out_hotspot_dir, f"{hotspot_key}_change_heatmap.png")
        Image.fromarray(heat_rgb).save(p_heat)

        # 3. Save Binary Mask
        p_mask = os.path.join(out_hotspot_dir, f"{hotspot_key}_binary_mask.png")
        Image.fromarray(mask).save(p_mask)

        # 4. Generate High-Visibility Annotated Detections Image
        # Bounding boxes highlighted in neon orange with bold labels
        annotated = img_post.copy()
        for idx, cand in enumerate(candidates):
            bx = cand.region.bbox_pixels
            if bx:
                x1, y1, x2, y2 = bx
                # Thick high-visibility rectangle
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 60, 0), 2)
                # Label with background pill for clear readability
                label = f"#{idx+1} {cand.candidate_id[-7:]} p={cand.confidence:.2f}"
                cv2.putText(annotated, label, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 2)
                cv2.putText(annotated, label, (x1, max(y1 - 4, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

        p_annot = os.path.join(out_hotspot_dir, f"{hotspot_key}_change_annotations.png")
        Image.fromarray(annotated).save(p_annot)

        # 5. Generate 4-Panel High-Resolution Comparison Montage
        h, w = img_pre.shape[:2]
        montage = np.zeros((h, w * 4, 3), dtype=np.uint8)
        montage[:, :w] = img_pre
        montage[:, w : w * 2] = img_post
        montage[:, w * 2 : w * 3] = heat_rgb
        montage[:, w * 3 :] = annotated

        # Widescreen titles
        font = cv2.FONT_HERSHEY_SIMPLEX
        t1_str = meta.get("pre_datetime", "T1")[:10]
        t2_str = meta.get("post_datetime", "T2")[:10]
        cv2.putText(montage, f"Pre-Change T1 ({t1_str})", (12, 25), font, 0.55, (255, 255, 255), 1)
        cv2.putText(montage, f"Post-Change T2 ({t2_str})", (w + 12, 25), font, 0.55, (255, 255, 255), 1)
        cv2.putText(montage, "Change Intensity Heatmap", (w * 2 + 12, 25), font, 0.55, (255, 255, 255), 1)
        cv2.putText(montage, f"Change Locations ({len(candidates)} Found)", (w * 3 + 12, 25), font, 0.55, (0, 255, 255), 1)

        p_montage = os.path.join(out_hotspot_dir, f"{hotspot_key}_visual_comparison_montage.png")
        Image.fromarray(montage).save(p_montage)

        # 6. Extract Top Close-Up Inspection Chips
        # Sorted by change area descending
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
            chip_img = self._extract_zoom_chip(img_pre, img_post, bx, padding=20)
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

        # Summary metadata
        total_change_m2 = sum(item["area_m2"] for item in cand_dicts)
        summary = {
            "hotspot_key": hotspot_key,
            "name": info["name"],
            "description": info["description"],
            "dates": {"t1": t1_str, "t2": t2_str},
            "subpixel_shift": {"dx_px": dx, "dy_px": dy},
            "gsd_meters_per_pixel": gsd,
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
                "widescreen_montage": os.path.basename(p_montage),
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
        padding: int = 20,
        height: int = 140,
    ) -> np.ndarray:
        """Extract high-resolution side-by-side chip (Pre, Post, Diff, Annotation)."""
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

        # Annotated
        annot = c_post.copy()
        cv2.rectangle(annot, (x1 - px1, y1 - py1), (x2 - px1, y2 - py1), (255, 60, 0), 2)

        panels = [c_pre, c_post, diff_rgb, annot]
        scaled = []
        for p in panels:
            ph, pw = p.shape[:2]
            scale = height / max(ph, 1)
            nw = max(int(pw * scale), 1)
            scaled.append(cv2.resize(p, (nw, height), interpolation=cv2.INTER_LINEAR))

        sep = np.ones((height, 3, 3), dtype=np.uint8) * 50
        return np.hstack([scaled[0], sep, scaled[1], sep, scaled[2], sep, scaled[3]])

    def generate_comprehensive_report(self, summaries: List[Dict[str, Any]]) -> str:
        """Write a comprehensive visual change verification guide in markdown."""
        out_md = os.path.join(self.exports_dir, "ZOOMED_CHANGE_ANALYSIS.md")
        lines = [
            "# Real Zoomed Satellite Change Verification Report",
            "",
            "**Module:** SatQuery (Computer Vision & Spatial Analytics)  ",
            "**Sensor:** European Space Agency (ESA) Sentinel-2 Level-2A (Optical Surface Reflectance)  ",
            "**Resolution:** Zoomed Corridor GSD ($5.0\\text{ m/pixel}$ effective)  ",
            "**Observation Baseline:** ~2-Year Bitemporal Interval ($2021/2022 \\to 2023/2024$)  ",
            "",
            "---",
            "",
            "## 1. Executive Summary & Purpose",
            "",
            "This report documents high-resolution zoomed satellite imagery acquired over strategic Indian infrastructure corridors to **definitively identify, localize, and state where physical ground changes occurred**.",
            "",
            "By focusing on tightly bounded geographic extents, optical resolution is maximized, allowing human analysts and reviewers to visually inspect individual building construction footprints, highway widening lanes, and land clearing activities.",
            "",
            "All downloaded and generated imagery is organized into dedicated separate directories:",
            "- **Raw Downloaded Bitemporal Scenes:** `SatQuery/data/zoomed_real_scenes/`",
            "- **Annotated Verification Maps & Inspection Chips:** `SatQuery/exports/zoomed_change_verification/`",
            "",
            "---",
            "",
            "## 2. Multi-Corridor Zoomed Verification Summary",
            "",
            "| Corridor Identifier | Region Name | Geographic Coordinates | Baseline Period | Targets Found | Change Footprint |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]

        for s in summaries:
            dt = s["dates"]
            lines.append(
                f"| **`{s['hotspot_key']}`** | {s['name']} | `{s.get('description', '')[:35]}...` | "
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
                f"- **Sub-Pixel Spatial Shift:** $\\Delta x = {s['subpixel_shift']['dx_px']}\\text{{ px}}, \\Delta y = {s['subpixel_shift']['dy_px']}\\text{{ px}}$",
                f"- **Detection Volume:** **{s['total_candidates_detected']} distinct change targets** covering **{s['total_change_footprint_ha']} hectares**",
                "",
                "#### Visual Inspection Artifacts:",
                f"- **Widescreen 4-Panel Comparison:** [`{f['widescreen_montage']}`]({k}/{f['widescreen_montage']})",
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
            "## 4. How to Inspect & Validate Changes",
            "",
            "1. **View the 4-Panel Widescreen Montages:**",
            "   Open any `*_visual_comparison_montage.png` to compare Pre $T_1$, Post $T_2$, Difference Heatmap, and Annotated Boxes side-by-side.",
            "2. **Check High-Visibility Annotation Outlines:**",
            "   Open `*_change_annotations.png` where every confirmed change location is framed by an orange bounding box with confidence score.",
            "3. **Inspect Close-Up Chips:**",
            "   Examine individual `inspection_chips/` images to verify localized building construction and earthwork.",
            "",
        ])

        with open(out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return out_md
