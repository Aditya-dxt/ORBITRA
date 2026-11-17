"""Real satellite imagery pipeline for Indian geographic regions.

Fetches, caches, aligns, and processes genuine bi-temporal Sentinel-2 Level-2A imagery
across key Indian regions:
1. kanpur_bhauti: Kanpur / Bhauti (UP), NH-19 industrial corridor near PSIT
2. delhi_ncr: New Delhi / Gurugram urban expansion corridor
3. bengaluru_tech: Bengaluru / Electronic City infrastructure corridor
4. chennai_sriperumbudur: Chennai / Sriperumbudur manufacturing hub
"""

import io
import json
import os
import urllib.request
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image

# Indian geographic mission zones
INDIAN_MISSION_ZONES: Dict[str, Dict] = {
    "kanpur_bhauti": {
        "name": "Kanpur / Bhauti Corridor, Uttar Pradesh",
        "home_lat": 26.447000,
        "home_lon": 80.198000,
        "bbox": [80.14, 26.40, 80.26, 26.50],
        "pre_date_range": "2021-11-01T00:00:00Z/2021-12-31T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2023-12-31T00:00:00Z",
        "description": "High-growth industrial and highway construction along NH-19 near PSIT Kanpur",
    },
    "delhi_ncr": {
        "name": "Delhi NCR / Gurugram Development Corridor",
        "home_lat": 28.480000,
        "home_lon": 77.050000,
        "bbox": [77.00, 28.42, 77.10, 28.52],
        "pre_date_range": "2021-10-01T00:00:00Z/2021-12-31T00:00:00Z",
        "post_date_range": "2023-10-01T00:00:00Z/2023-12-31T00:00:00Z",
        "description": "Rapid commercial and residential urban spread in NCR",
    },
    "bengaluru_tech": {
        "name": "Bengaluru Electronic City Infrastructure",
        "home_lat": 12.850000,
        "home_lon": 77.660000,
        "bbox": [77.60, 12.80, 77.72, 12.90],
        "pre_date_range": "2021-11-01T00:00:00Z/2022-01-31T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2024-01-31T00:00:00Z",
        "description": "Metro rail expansion and tech park infrastructure developments",
    },
    "chennai_sriperumbudur": {
        "name": "Chennai / Sriperumbudur Industrial Corridor",
        "home_lat": 12.980000,
        "home_lon": 79.960000,
        "bbox": [79.90, 12.92, 80.02, 13.02],
        "pre_date_range": "2021-11-01T00:00:00Z/2022-02-28T00:00:00Z",
        "post_date_range": "2023-11-01T00:00:00Z/2024-02-28T00:00:00Z",
        "description": "Automotive and electronics manufacturing land development",
    },
}


class IndiaSatelliteDataLoader:
    """Manages acquisition, caching, and preprocessing of real Indian satellite imagery."""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            cache_dir = os.path.join(base_dir, "data", "india_scenes")
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
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
        """Search STAC API for lowest cloud cover Sentinel-2 L2A scene."""
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
            preview_url = item["assets"]["rendered_preview"]["href"]
            return preview_url, scene_id, obs_dt

    def _download_image(self, url: str) -> np.ndarray:
        """Download and decode image array from URL with SAS token authorization."""
        sas_token = self._get_planetary_sas_token()
        signed_url = url + ("&" if "?" in url else "?") + sas_token
        req = urllib.request.Request(signed_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_bytes = resp.read()
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return np.array(pil_img)

    def get_indian_scene_pair(
        self,
        zone_key: str = "kanpur_bhauti",
        crop_size: int = 512,
        force_download: bool = False,
    ) -> Dict:
        """Fetch or load cached real bitemporal satellite image pair over an Indian zone.
        
        Returns:
            Dict containing:
                'zone_key': Zone identifier
                'zone_name': Human-readable name
                'img_pre': Pre-change RGB uint8 ndarray
                'img_post': Post-change RGB uint8 ndarray
                'pre_meta': Dict with scene ID and timestamp
                'post_meta': Dict with scene ID and timestamp
                'home_lat': Latitude of zone origin
                'home_lon': Longitude of zone origin
                'alignment_shift_pixels': (dx, dy)
        """
        if zone_key not in INDIAN_MISSION_ZONES:
            raise ValueError(f"Unknown zone '{zone_key}'. Available: {list(INDIAN_MISSION_ZONES.keys())}")

        zone_info = INDIAN_MISSION_ZONES[zone_key]
        pre_file = os.path.join(self.cache_dir, f"{zone_key}_pre_real.png")
        post_file = os.path.join(self.cache_dir, f"{zone_key}_post_real.png")
        meta_file = os.path.join(self.cache_dir, f"{zone_key}_meta.json")

        if not force_download and os.path.exists(pre_file) and os.path.exists(post_file) and os.path.exists(meta_file):
            # Load from local cache
            img_pre = np.array(Image.open(pre_file).convert("RGB"))
            img_post = np.array(Image.open(post_file).convert("RGB"))
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            # Fetch from live Sentinel-2 STAC
            print(f"🛰️  Acquiring real Sentinel-2 satellite data for {zone_info['name']}...")
            url_pre, id_pre, dt_pre = self._query_stac_scene(zone_info["bbox"], zone_info["pre_date_range"])
            url_post, id_post, dt_post = self._query_stac_scene(zone_info["bbox"], zone_info["post_date_range"])

            raw_pre = self._download_image(url_pre)
            raw_post = self._download_image(url_post)

            # Center crop to standard analysis dimension
            h, w = raw_pre.shape[:2]
            cx, cy = w // 2, h // 2
            half = crop_size // 2

            crop_pre = raw_pre[cy - half : cy + half, cx - half : cx + half]
            crop_post = raw_post[cy - half : cy + half, cx - half : cx + half]

            # Harmonize shapes
            if crop_pre.shape != crop_post.shape:
                crop_post = cv2.resize(crop_post, (crop_pre.shape[1], crop_pre.shape[0]))

            img_pre = crop_pre
            img_post = crop_post

            metadata = {
                "zone_key": zone_key,
                "zone_name": zone_info["name"],
                "home_lat": zone_info["home_lat"],
                "home_lon": zone_info["home_lon"],
                "bbox": zone_info["bbox"],
                "pre_scene_id": id_pre,
                "pre_datetime": dt_pre,
                "post_scene_id": id_post,
                "post_datetime": dt_post,
                "source": "ESA Sentinel-2 Level-2A (Optical Surface Reflectance)",
            }

            # Cache locally
            Image.fromarray(img_pre).save(pre_file)
            Image.fromarray(img_post).save(post_file)
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            print(f"   ✓ Cached real imagery pair ({img_pre.shape[1]}x{img_pre.shape[0]}) to {self.cache_dir}")

        # Compute spatial co-registration shift
        gray_a = cv2.cvtColor(img_pre, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray_b = cv2.cvtColor(img_post, cv2.COLOR_RGB2GRAY).astype(np.float32)
        shift, _ = cv2.phaseCorrelate(gray_a, gray_b)
        dx, dy = round(float(shift[0]), 2), round(float(shift[1]), 2)

        return {
            "zone_key": zone_key,
            "zone_name": zone_info["name"],
            "img_pre": img_pre,
            "img_post": img_post,
            "metadata": metadata,
            "home_lat": zone_info["home_lat"],
            "home_lon": zone_info["home_lon"],
            "alignment_shift_pixels": (dx, dy),
        }
