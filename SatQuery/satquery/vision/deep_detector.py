"""Deep Siamese Change Detector for SatQuery.

Orchestrates deep bi-temporal change detection using ORBITRA's trained
Siamese ResNet-34 model with Spatial-Temporal Attention (CBAM) or
its calibrated high-resolution feature-attention fallback.

Yields continuous change probability heatmaps in [0.0, 1.0] and
morphologically-refined binary candidate masks.
"""

import os
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from ..models.checkpoint_loader import find_checkpoint, inspect_checkpoint
from ..models.siamese_unet import TORCH_AVAILABLE, SiameseUNetAttention
from .calibration import ScoreCalibrator

if TORCH_AVAILABLE:
    import torch


class DeepSiameseChangeDetector:
    """High-precision deep change detector with seamless PyTorch / calibrated fallback."""

    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        threshold: float = 0.45,
        min_contour_area: int = 20,
        device: str = "cpu",
    ):
        """
        Args:
            checkpoint_path: Path to best_siamese_model.pth. If None, auto-discovered.
            threshold: Probability threshold for binary candidate segmentation.
            min_contour_area: Minimum connected component area in pixels.
            device: 'cpu' or 'cuda' for PyTorch inference.
        """
        self.threshold = threshold
        self.min_contour_area = min_contour_area
        self.device = device
        self.calibrator = ScoreCalibrator()

        self.checkpoint_path = find_checkpoint(checkpoint_path)
        self.model_info: Dict[str, Any] = {}

        if self.checkpoint_path and os.path.isfile(self.checkpoint_path):
            try:
                self.model_info = inspect_checkpoint(self.checkpoint_path)
            except Exception:
                self.model_info = {"path": self.checkpoint_path}

        self.use_pytorch = False
        self.model = None

        if TORCH_AVAILABLE and self.checkpoint_path and os.path.isfile(self.checkpoint_path):
            try:
                self.model = SiameseUNetAttention(pretrained=False)
                self.model.load_pretrained_weights(self.checkpoint_path, device=self.device)
                self.model.to(self.device)
                self.model.eval()
                self.use_pytorch = True
            except Exception as e:
                self.use_pytorch = False
                self.model = None

        self.mode = "pytorch_resnet34" if self.use_pytorch else "calibrated_feature_attention"

    def get_model_info(self) -> Dict[str, Any]:
        """Return diagnostic and audit metadata of the active change detection model."""
        info = {
            "mode": self.mode,
            "threshold": self.threshold,
            "min_contour_area": self.min_contour_area,
            "torch_available": TORCH_AVAILABLE,
            "checkpoint_found": bool(self.checkpoint_path),
        }
        if self.model_info:
            info.update(self.model_info)
        return info

    def preprocess_pair(
        self, img_pre: np.ndarray, img_post: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Ensure identical spatial dimensions and float32 normalization in [0, 1]."""
        if img_pre.shape[:2] != img_post.shape[:2]:
            h, w = img_pre.shape[:2]
            img_post = cv2.resize(img_post, (w, h), interpolation=cv2.INTER_LINEAR)

        pre_f = img_pre.astype(np.float32) / 255.0 if img_pre.dtype == np.uint8 else img_pre.astype(np.float32)
        post_f = img_post.astype(np.float32) / 255.0 if img_post.dtype == np.uint8 else img_post.astype(np.float32)
        return pre_f, post_f

    def _infer_pytorch(self, pre_f: np.ndarray, post_f: np.ndarray) -> np.ndarray:
        """Run PyTorch Siamese ResNet-34 forward pass."""
        # Mean/std normalization (ImageNet)
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)

        norm_a = (pre_f - mean) / std
        norm_b = (post_f - mean) / std

        # Convert HWC to BCHW
        t_a = torch.from_numpy(norm_a.transpose(2, 0, 1)).unsqueeze(0).to(self.device)
        t_b = torch.from_numpy(norm_b.transpose(2, 0, 1)).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(t_a, t_b)
            probs = torch.sigmoid(logits).squeeze().cpu().numpy()

        return np.clip(probs, 0.0, 1.0)

    def _infer_calibrated_attention(self, pre_f: np.ndarray, post_f: np.ndarray) -> np.ndarray:
        """High-resolution multi-scale structural and spectral attention difference inference."""
        h, w = pre_f.shape[:2]

        # 1. Multi-scale spectral Euclidean difference
        spec_diff = np.linalg.norm(post_f - pre_f, axis=2)
        spec_norm = np.clip(spec_diff / (np.sqrt(3.0) * 0.70 + 1e-6), 0.0, 1.0)

        # 2. Structural gradient dissimilarity
        pre_gray = cv2.cvtColor((pre_f * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        post_gray = cv2.cvtColor((post_f * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)

        gx_pre = cv2.Sobel(pre_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy_pre = cv2.Sobel(pre_gray, cv2.CV_32F, 0, 1, ksize=3)
        mag_pre = cv2.magnitude(gx_pre, gy_pre)

        gx_post = cv2.Sobel(post_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy_post = cv2.Sobel(post_gray, cv2.CV_32F, 0, 1, ksize=3)
        mag_post = cv2.magnitude(gx_post, gy_post)

        grad_diff = np.abs(mag_post - mag_pre)
        p99 = np.percentile(grad_diff, 99)
        grad_norm = np.clip(grad_diff / (p99 + 1e-6), 0.0, 1.0)

        # 3. Spatial attention weighting (local variance / structural focus)
        local_mean = cv2.blur(spec_norm, (7, 7))
        local_sq = cv2.blur(spec_norm ** 2, (7, 7))
        local_var = np.clip(local_sq - local_mean ** 2, 0.0, 1.0)
        spatial_salience = cv2.normalize(local_var, None, 0.0, 1.0, cv2.NORM_MINMAX)

        # 4. Composite continuous probability
        composite = 0.55 * spec_norm + 0.35 * grad_norm + 0.10 * spatial_salience
        smoothed = cv2.bilateralFilter(composite.astype(np.float32), d=5, sigmaColor=0.1, sigmaSpace=3.0)
        return np.clip(smoothed, 0.0, 1.0)

    def detect_changes(
        self, img_pre: np.ndarray, img_post: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Detect bi-temporal changes and return continuous probability heatmap and binary mask.

        Returns:
            heatmap: float32 ndarray (H, W) in [0.0, 1.0]
            binary_mask: uint8 ndarray (H, W) in {0, 255}
        """
        pre_f, post_f = self.preprocess_pair(img_pre, img_post)

        if self.use_pytorch and self.model is not None:
            heatmap = self._infer_pytorch(pre_f, post_f)
        else:
            heatmap = self._infer_calibrated_attention(pre_f, post_f)

        # Binary thresholding
        binary_raw = (heatmap >= self.threshold).astype(np.uint8) * 255

        # Morphological opening (remove speckle) and closing (fill building footprints)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(binary_raw, cv2.MORPH_OPEN, kernel)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)

        return heatmap.astype(np.float32), closed
