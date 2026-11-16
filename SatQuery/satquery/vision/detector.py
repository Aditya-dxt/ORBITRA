"""Baseline Change Detector for SatQuery.

Implements established differential multi-scale computer-vision change detection:
1. Radiometric and spectral normalization
2. Normalized Euclidean spectral difference
3. Spatial gradient / texture dissimilarity (Sobel gradient magnitudes)
4. Morphological noise suppression (opening/closing)
5. Continuous change probability heatmap generation in [0.0, 1.0]
6. Binary change mask thresholding
"""

import cv2
import numpy as np
from typing import Dict, Tuple, Optional


class BaselineChangeDetector:
    """Multi-scale differential change detector for bi-temporal satellite image pairs."""

    def __init__(
        self,
        threshold: float = 0.35,
        min_contour_area: int = 15,
        morph_kernel_size: int = 3,
        spectral_weight: float = 0.65,
        gradient_weight: float = 0.35,
    ):
        """
        Args:
            threshold: Decision threshold on continuous heatmap for binary candidate flagging.
            min_contour_area: Minimum connected pixel area to qualify as candidate change.
            morph_kernel_size: Kernel dimension for morphological noise filtering.
            spectral_weight: Weight for spectral Euclidean distance.
            gradient_weight: Weight for gradient / structural dissimilarity.
        """
        self.threshold = threshold
        self.min_contour_area = min_contour_area
        self.morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (morph_kernel_size, morph_kernel_size)
        )
        self.spectral_weight = spectral_weight
        self.gradient_weight = gradient_weight

    def preprocess_pair(
        self, img_pre: np.ndarray, img_post: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Validate, equalize dimensions, and normalize image pair to float32 [0, 1]."""
        if img_pre.shape[:2] != img_post.shape[:2]:
            h, w = img_pre.shape[:2]
            img_post = cv2.resize(img_post, (w, h), interpolation=cv2.INTER_LINEAR)

        # Convert to RGB float32 in [0, 1]
        pre_f = img_pre.astype(np.float32) / 255.0 if img_pre.dtype == np.uint8 else img_pre.astype(np.float32)
        post_f = img_post.astype(np.float32) / 255.0 if img_post.dtype == np.uint8 else img_post.astype(np.float32)

        return pre_f, post_f

    def compute_difference_heatmap(
        self, img_pre: np.ndarray, img_post: np.ndarray
    ) -> np.ndarray:
        """Compute continuous change intensity heatmap in [0.0, 1.0]."""
        pre_f, post_f = self.preprocess_pair(img_pre, img_post)

        # 1. Multi-spectral Euclidean color difference
        spectral_diff = np.linalg.norm(post_f - pre_f, axis=2)
        # Normalize to [0, 1]
        spectral_norm = np.clip(spectral_diff / (np.sqrt(3.0) * 0.75 + 1e-6), 0.0, 1.0)

        # 2. Structural gradient dissimilarity
        pre_gray = cv2.cvtColor((pre_f * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        post_gray = cv2.cvtColor((post_f * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)

        # Sobel gradients
        gx_pre = cv2.Sobel(pre_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy_pre = cv2.Sobel(pre_gray, cv2.CV_32F, 0, 1, ksize=3)
        mag_pre = cv2.magnitude(gx_pre, gy_pre)

        gx_post = cv2.Sobel(post_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy_post = cv2.Sobel(post_gray, cv2.CV_32F, 0, 1, ksize=3)
        mag_post = cv2.magnitude(gx_post, gy_post)

        grad_diff = np.abs(mag_post - mag_pre)
        grad_norm = np.clip(grad_diff / (np.percentile(grad_diff, 99) + 1e-6), 0.0, 1.0)

        # 3. Weighted composite continuous heatmap
        heatmap = (self.spectral_weight * spectral_norm) + (self.gradient_weight * grad_norm)

        # 4. Bilateral smoothing to preserve structural boundaries while reducing noise
        heatmap_smoothed = cv2.bilateralFilter(
            heatmap.astype(np.float32), d=5, sigmaColor=0.1, sigmaSpace=3.0
        )
        return np.clip(heatmap_smoothed, 0.0, 1.0)

    def detect_changes(
        self, img_pre: np.ndarray, img_post: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Detect changes and return (continuous_heatmap, binary_mask).
        
        Returns:
            heatmap: float32 ndarray of shape (H, W) in [0.0, 1.0]
            binary_mask: uint8 ndarray of shape (H, W) in {0, 255}
        """
        heatmap = self.compute_difference_heatmap(img_pre, img_post)

        # Thresholding
        binary_raw = (heatmap >= self.threshold).astype(np.uint8) * 255

        # Morphological opening (removes speckle noise) and closing (closes holes in buildings)
        opened = cv2.morphologyEx(binary_raw, cv2.MORPH_OPEN, self.morph_kernel)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, self.morph_kernel)

        return heatmap, closed
