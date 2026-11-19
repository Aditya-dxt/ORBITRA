"""Evaluation package for SatQuery."""

from .metrics import VisionEvaluator, compute_bbox_iou, compute_pixel_metrics
from .reliability_diagram import (
    compute_reliability_data,
    render_ascii_reliability_diagram,
    generate_svg_reliability_diagram,
)

__all__ = [
    "VisionEvaluator",
    "compute_bbox_iou",
    "compute_pixel_metrics",
    "compute_reliability_data",
    "render_ascii_reliability_diagram",
    "generate_svg_reliability_diagram",
]
