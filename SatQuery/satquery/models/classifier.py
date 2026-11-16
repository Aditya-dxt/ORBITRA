"""Semantic Change Classifier for SatQuery candidate regions.

Analyzes cropped change patches to classify detected changes into operational categories:
- urban_building_construction: New foundations, structures, roofing, or built-up spread.
- road_infrastructure: Linear grading, paving, asphalt, or transportation works.
- vegetation_clearing: Deforestation, crop clearing, tree felling, or ground exposure.
- natural_variation: Unaltered background, moisture variation, or seasonal grass changes.
"""

import cv2
import numpy as np
from typing import Dict, Tuple


class SemanticChangeClassifier:
    """Classifies candidate change patches using colorimetry, structural morphology, and texture."""

    CLASSES = [
        "urban_building_construction",
        "road_infrastructure",
        "vegetation_clearing",
        "natural_variation",
    ]

    def __init__(self):
        pass

    def classify_patch(
        self, patch_pre: np.ndarray, patch_post: np.ndarray
    ) -> Tuple[str, float]:
        """Classify a bitemporal change patch and return (class_name, class_confidence).
        
        Args:
            patch_pre: RGB uint8 crop from pre-change image.
            patch_post: RGB uint8 crop from post-change image.
            
        Returns:
            Tuple of (predicted_change_str, classification_confidence_float)
        """
        if patch_post.size == 0:
            return "natural_variation", 0.50

        # Resize to standard analysis size if small
        h, w = patch_post.shape[:2]
        if h < 16 or w < 16:
            patch_post = cv2.resize(patch_post, (32, 32), interpolation=cv2.INTER_LINEAR)
            if patch_pre.size > 0:
                patch_pre = cv2.resize(patch_pre, (32, 32), interpolation=cv2.INTER_LINEAR)

        # 1. Color and vegetation indices (ExG - Excess Green, NDVI proxy)
        post_f = patch_post.astype(np.float32) / 255.0
        pre_f = patch_pre.astype(np.float32) / 255.0 if patch_pre.size > 0 else post_f

        r_post, g_post, b_post = post_f[:, :, 0], post_f[:, :, 1], post_f[:, :, 2]
        r_pre, g_pre, b_pre = pre_f[:, :, 0], pre_f[:, :, 1], pre_f[:, :, 2]

        # Excess Green index (2G - R - B)
        exg_pre = np.mean(2.0 * g_pre - r_pre - b_pre)
        exg_post = np.mean(2.0 * g_post - r_post - b_post)
        green_loss = exg_pre - exg_post

        # 2. Brightness and high-frequency edge analysis (buildings and roads have strong edges)
        gray_post = cv2.cvtColor(patch_post, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray_post, 50, 150)
        edge_density = float(np.mean(edges > 0))

        # Aspect ratio / linearity
        aspect_ratio = max(w / max(h, 1), h / max(w, 1))

        # Brightness shift (construction typically brightens ground due to concrete, sand, or cleared soil)
        brightness_pre = np.mean(pre_f)
        brightness_post = np.mean(post_f)
        brightness_delta = brightness_post - brightness_pre

        # Decision scoring logic
        scores = {
            "urban_building_construction": 0.0,
            "road_infrastructure": 0.0,
            "vegetation_clearing": 0.0,
            "natural_variation": 0.1,
        }

        # Vegetation loss signal
        if green_loss > 0.12:
            scores["vegetation_clearing"] += 0.65 + min(green_loss * 1.5, 0.3)
        elif green_loss > 0.05:
            scores["vegetation_clearing"] += 0.35

        # Urban building signals: high edge density, compact shapes, brightness shift
        if edge_density > 0.15 and aspect_ratio < 2.5:
            scores["urban_building_construction"] += 0.60 + min(edge_density, 0.35)
        elif edge_density > 0.08:
            scores["urban_building_construction"] += 0.30

        # Road infrastructure signals: elongated / high aspect ratio, moderate edge density
        if aspect_ratio >= 2.5 and edge_density > 0.08:
            scores["road_infrastructure"] += 0.60 + min(aspect_ratio * 0.08, 0.35)

        # Brightness / soil exposure without strong edges
        if brightness_delta > 0.20 and edge_density <= 0.12 and green_loss <= 0.08:
            scores["vegetation_clearing"] += 0.40
            scores["urban_building_construction"] += 0.30

        # Normalization
        best_class = max(scores, key=scores.get)
        max_score = scores[best_class]

        # Convert to probability confidence
        if max_score <= 0.15:
            return "natural_variation", 0.60

        total_score = sum(scores.values()) + 1e-6
        confidence = float(np.clip(max_score / total_score, 0.55, 0.95))
        return best_class, round(confidence, 3)
