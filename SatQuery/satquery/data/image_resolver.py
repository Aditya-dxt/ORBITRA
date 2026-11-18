"""Image Pair Resolver for SatQuery and ARES integration.

Resolves an image_pair_id (e.g. 'pair_levir_test_042', 'pair_sentinel2_kanpur_bhauti')
to its corresponding source bi-temporal imagery (img_pre, img_post) for candidate
crop extraction, visual verification, and deep detector re-inference.
"""

import os
from typing import Dict, NamedTuple, Optional, Tuple
import numpy as np
from PIL import Image

from .synthetic_sample_data import generate_benchmark_pair


class ResolvedImagePair(NamedTuple):
    """Container for resolved bi-temporal imagery and provenance metadata."""
    img_pre: np.ndarray
    img_post: np.ndarray
    image_pair_id: str
    source_type: str        # e.g., "DISK_FILE_REAL", "DISK_FILE_BENCHMARK", "DETERMINISTIC_SYNTHETIC"
    is_synthetic: bool
    description: str
    pre_path: Optional[str] = None
    post_path: Optional[str] = None


class ImagePairResolver:
    """Resolves candidate image_pair_id identifiers to actual image arrays."""

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            # SatQuery/data
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            data_root = os.path.join(base_dir, "data")
        self.data_root = data_root
        self.sample_pairs_dir = os.path.join(self.data_root, "sample_pairs")
        self.india_scenes_dir = os.path.join(self.data_root, "india_scenes")

    def resolve(self, image_pair_id: str) -> ResolvedImagePair:
        """Resolve image_pair_id to image arrays.

        Resolution strategy:
        1. Check for real Sentinel-2 cached imagery (e.g., pair_sentinel2_kanpur_bhauti).
        2. Check for cached benchmark PNGs on disk (e.g., scene_levir_042_{pre,post}.png).
        3. For canonical synthetic IDs (e.g., pair_levir_test_042), deterministically
           regenerate the benchmark pair if disk files are absent (e.g. clean git checkout).
        4. Fall back to generic search or deterministic fallback generator.
        """
        pid = image_pair_id.strip()

        # 1. Real Sentinel-2 Indian satellite scenes
        india_zone_map = {
            "pair_sentinel2_kanpur_bhauti": ("kanpur_bhauti", "Kanpur / Bhauti Corridor, UP (Sentinel-2 L2A)"),
            "pair_sentinel2_bengaluru_tech": ("bengaluru_tech", "Bengaluru Electronic City, KA (Sentinel-2 L2A)"),
            "pair_sentinel2_chennai_sriperumbudur": ("chennai_sriperumbudur", "Chennai / Sriperumbudur, TN (Sentinel-2 L2A)"),
            "pair_sentinel2_delhi_ncr": ("delhi_ncr", "Delhi NCR / Gurugram, DL/HR (Sentinel-2 L2A)"),
        }

        if pid in india_zone_map:
            zone_key, desc = india_zone_map[pid]
            pre_path = os.path.join(self.india_scenes_dir, f"{zone_key}_pre_real.png")
            post_path = os.path.join(self.india_scenes_dir, f"{zone_key}_post_real.png")

            if os.path.exists(pre_path) and os.path.exists(post_path):
                img_pre = np.array(Image.open(pre_path).convert("RGB"))
                img_post = np.array(Image.open(post_path).convert("RGB"))
                return ResolvedImagePair(
                    img_pre=img_pre,
                    img_post=img_post,
                    image_pair_id=pid,
                    source_type="DISK_FILE_REAL",
                    is_synthetic=False,
                    description=desc,
                    pre_path=pre_path,
                    post_path=post_path,
                )

        # 2. Canonical LEVIR-CD benchmark scenes
        levir_seed_map = {
            "pair_levir_test_042": (42, "scene_levir_042", "LEVIR-CD synthetic benchmark scene 042 (seed=42)"),
            "pair_scene_levir_042": (42, "scene_levir_042", "LEVIR-CD synthetic benchmark scene 042 (seed=42)"),
            "pair_scene_levir_088": (88, "scene_levir_088", "LEVIR-CD synthetic benchmark scene 088 (seed=88)"),
            "pair_scene_levir_105": (105, "scene_levir_105", "LEVIR-CD synthetic benchmark scene 105 (seed=105)"),
            "pair_benchmark_live": (42, "scene_levir_042", "Live synthetic benchmark scene (seed=42)"),
        }

        if pid in levir_seed_map:
            seed, base_name, desc = levir_seed_map[pid]
            pre_path = os.path.join(self.sample_pairs_dir, f"{base_name}_pre.png")
            post_path = os.path.join(self.sample_pairs_dir, f"{base_name}_post.png")

            if os.path.exists(pre_path) and os.path.exists(post_path):
                img_pre = np.array(Image.open(pre_path).convert("RGB"))
                img_post = np.array(Image.open(post_path).convert("RGB"))
                return ResolvedImagePair(
                    img_pre=img_pre,
                    img_post=img_post,
                    image_pair_id=pid,
                    source_type="DISK_FILE_BENCHMARK",
                    is_synthetic=True,
                    description=desc,
                    pre_path=pre_path,
                    post_path=post_path,
                )

            # If disk cache is not present (e.g. clean clone where data/ is gitignored),
            # deterministically synthesize the identical benchmark scene from seed
            scene = generate_benchmark_pair(seed=seed, size=(256, 256), num_buildings=3, has_road=True, has_clearing=True)
            return ResolvedImagePair(
                img_pre=scene["img_pre"],
                img_post=scene["img_post"],
                image_pair_id=pid,
                source_type="DETERMINISTIC_SYNTHETIC",
                is_synthetic=True,
                description=f"{desc} [regenerated from seed {seed}]",
                pre_path=None,
                post_path=None,
            )

        # 3. Fallback heuristic: search sample_pairs_dir
        if os.path.exists(self.sample_pairs_dir):
            for fname in os.listdir(self.sample_pairs_dir):
                if pid in fname and fname.endswith("_pre.png"):
                    base = fname[:-8]
                    pre_p = os.path.join(self.sample_pairs_dir, f"{base}_pre.png")
                    post_p = os.path.join(self.sample_pairs_dir, f"{base}_post.png")
                    if os.path.exists(post_p):
                        img_pre = np.array(Image.open(pre_p).convert("RGB"))
                        img_post = np.array(Image.open(post_p).convert("RGB"))
                        return ResolvedImagePair(
                            img_pre=img_pre,
                            img_post=img_post,
                            image_pair_id=pid,
                            source_type="DISK_FILE_GENERIC",
                            is_synthetic=True,
                            description=f"Generic benchmark pair '{base}'",
                            pre_path=pre_p,
                            post_path=post_p,
                        )

        # 4. Final fallback: deterministic synthetic scene
        scene = generate_benchmark_pair(seed=42, size=(256, 256), num_buildings=3, has_road=True, has_clearing=True)
        return ResolvedImagePair(
            img_pre=scene["img_pre"],
            img_post=scene["img_post"],
            image_pair_id=pid,
            source_type="DETERMINISTIC_SYNTHETIC_FALLBACK",
            is_synthetic=True,
            description=f"Deterministic synthetic fallback scene for unmapped pair '{pid}'",
            pre_path=None,
            post_path=None,
        )
