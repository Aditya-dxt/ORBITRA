"""Evaluation metrics and failure analysis for SatQuery vision pipeline.

Computes:
- Precision: TP / (TP + FP)
- Recall: TP / (TP + FN)
- F1-Score: 2 * (Precision * Recall) / (Precision + Recall)
- IoU (Intersection over Union / Jaccard Index): TP / (TP + FP + FN)
- Region-level candidate matching (at defined IoU threshold tau_IoU)
- Failure case analysis and error taxonomy logger
"""

from typing import Dict, List, Optional, Tuple
import numpy as np


def compute_pixel_metrics(
    prediction_mask: np.ndarray, ground_truth_mask: np.ndarray
) -> Dict[str, float]:
    """Compute pixel-level change detection metrics.
    
    Args:
        prediction_mask: Binary mask ndarray (H, W) where change is > 0.
        ground_truth_mask: Binary ground truth mask ndarray (H, W) where change is > 0.
        
    Returns:
        Dict containing precision, recall, f1_score, iou, accuracy, and pixel counts.
    """
    pred_bin = (prediction_mask > 0).astype(bool)
    gt_bin = (ground_truth_mask > 0).astype(bool)

    tp = int(np.sum(pred_bin & gt_bin))
    fp = int(np.sum(pred_bin & ~gt_bin))
    fn = int(np.sum(~pred_bin & gt_bin))
    tn = int(np.sum(~pred_bin & ~gt_bin))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1), 4),
        "iou": round(float(iou), 4),
        "accuracy": round(float(accuracy), 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def compute_bbox_iou(box_a: List[int], box_b: List[int]) -> float:
    """Compute IoU between two bounding boxes [xmin, ymin, xmax, ymax]."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area / union_area)


class VisionEvaluator:
    """Evaluates vision pipeline outputs and logs failure modes."""

    KNOWN_FAILURE_MODES = [
        "shadow_shift",           # Sun angle difference causing false tree or building edge changes
        "seasonal_coloration",    # Autumn foliage or dry grass color shift
        "sensor_speckle_noise",   # Sensor grain, co-registration residual
        "edge_misalignment",      # Sub-pixel boundary shift at contrast borders
        "off_nadir_occlusion",    # Viewing angle tilt obscuring ground surface
    ]

    def __init__(self, tau_iou: float = 0.5):
        """
        Args:
            tau_iou: Minimum IoU threshold for a candidate region to match a ground truth region.
        """
        self.tau_iou = tau_iou

    def evaluate_scene(
        self,
        prediction_mask: np.ndarray,
        ground_truth_mask: np.ndarray,
        candidate_boxes: Optional[List[List[int]]] = None,
        ground_truth_boxes: Optional[List[List[int]]] = None,
    ) -> Dict:
        """Run full scene-level evaluation returning pixel and region metrics."""
        metrics = compute_pixel_metrics(prediction_mask, ground_truth_mask)

        # Region-level matching
        region_tp = 0
        region_fp = 0
        region_fn = 0

        if candidate_boxes is not None and ground_truth_boxes is not None:
            matched_gt = set()
            for cand_box in candidate_boxes:
                best_iou = 0.0
                best_gt_idx = -1
                for gt_idx, gt_box in enumerate(ground_truth_boxes):
                    if gt_idx in matched_gt:
                        continue
                    iou_val = compute_bbox_iou(cand_box, gt_box)
                    if iou_val > best_iou:
                        best_iou = iou_val
                        best_gt_idx = gt_idx

                if best_iou >= self.tau_iou and best_gt_idx >= 0:
                    region_tp += 1
                    matched_gt.add(best_gt_idx)
                else:
                    region_fp += 1

            region_fn = len(ground_truth_boxes) - len(matched_gt)
            r_prec = region_tp / (region_tp + region_fp) if (region_tp + region_fp) > 0 else 0.0
            r_rec = region_tp / (region_tp + region_fn) if (region_tp + region_fn) > 0 else 0.0
            r_f1 = (2 * r_prec * r_rec) / (r_prec + r_rec) if (r_prec + r_rec) > 0 else 0.0

            metrics["region_precision"] = round(r_prec, 4)
            metrics["region_recall"] = round(r_rec, 4)
            metrics["region_f1"] = round(r_f1, 4)
            metrics["region_tp"] = region_tp
            metrics["region_fp"] = region_fp
            metrics["region_fn"] = region_fn

        return metrics
