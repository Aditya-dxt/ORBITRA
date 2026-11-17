"""End-to-end vision pipeline for SatQuery.

Runs:
1. Image pair loading and preprocessing
2. Spatial alignment check
3. Baseline differential change detection
4. Candidate region extraction and contour bounding boxes
5. Semantic classification
6. Confidence calibration and uncertainty quantification
7. Spatial georeferencing into local metric grid and geodetic coordinates
8. Strict schema validation and JSON export for ARES
"""

import json
import os
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from .data.synthetic_sample_data import generate_benchmark_pair
from .evaluation.metrics import VisionEvaluator
from .models.classifier import SemanticChangeClassifier
from .schemas.candidate_record import SatQueryCandidateRecord
from .vision.calibration import ScoreCalibrator
from .vision.candidate_generator import CandidateGenerator
from .vision.deep_detector import DeepSiameseChangeDetector
from .vision.detector import BaselineChangeDetector
from .vision.georeferencing import MissionGeoreferencer


class SatQueryPipeline:
    """Master pipeline orchestrating vision change detection to versioned ARES candidate export."""

    def __init__(
        self,
        threshold: float = 0.35,
        min_pixel_area: int = 25,
        georeferencer: Optional[MissionGeoreferencer] = None,
        calibrator: Optional[ScoreCalibrator] = None,
        schema_version: str = "v1.0.0-provisional",
        model_type: str = "baseline",
        checkpoint_path: Optional[str] = None,
        detector: Optional[Union[BaselineChangeDetector, DeepSiameseChangeDetector]] = None,
    ):
        self.model_type = model_type
        if detector is not None:
            self.detector = detector
        elif model_type == "deep_siamese":
            self.detector = DeepSiameseChangeDetector(
                checkpoint_path=checkpoint_path,
                threshold=threshold,
                min_contour_area=min_pixel_area,
            )
        else:
            self.detector = BaselineChangeDetector(threshold=threshold, min_contour_area=min_pixel_area)

        self.georeferencer = georeferencer or MissionGeoreferencer()
        self.calibrator = calibrator or ScoreCalibrator()
        self.classifier = SemanticChangeClassifier()
        self.candidate_generator = CandidateGenerator(
            georeferencer=self.georeferencer,
            calibrator=self.calibrator,
            classifier=self.classifier,
            min_pixel_area=min_pixel_area,
            default_schema_version=schema_version,
        )
        self.evaluator = VisionEvaluator(tau_iou=0.5)

    def process_pair(
        self,
        img_pre: np.ndarray,
        img_post: np.ndarray,
        image_pair_id: str = "pair_levir_001",
        timestamp: Optional[str] = None,
        ground_truth_mask: Optional[np.ndarray] = None,
        ground_truth_boxes: Optional[List[List[int]]] = None,
    ) -> Dict:
        """Execute change detection, candidate generation, and evaluation on an image pair.
        
        Returns:
            Dict containing:
                'candidates': List of SatQueryCandidateRecord instances
                'candidate_dicts': List of schema-validated JSON dictionaries
                'heatmap': Continuous float32 heatmap
                'binary_mask': Thresholded change mask
                'metrics': Evaluation metrics dict (if ground truth provided)
        """
        # 1. Detection
        heatmap, binary_mask = self.detector.detect_changes(img_pre, img_post)

        # 2. Candidate generation
        candidates = self.candidate_generator.generate_candidates(
            img_pre=img_pre,
            img_post=img_post,
            binary_mask=binary_mask,
            heatmap=heatmap,
            image_pair_id=image_pair_id,
            timestamp=timestamp,
        )

        # 3. Serialize to schema-validated dictionaries
        candidate_dicts = [cand.model_dump() for cand in candidates]

        # 4. Vision evaluation if ground truth is supplied
        metrics = None
        if ground_truth_mask is not None:
            cand_boxes = [cand.region.bbox_pixels for cand in candidates if cand.region.bbox_pixels]
            metrics = self.evaluator.evaluate_scene(
                prediction_mask=binary_mask,
                ground_truth_mask=ground_truth_mask,
                candidate_boxes=cand_boxes,
                ground_truth_boxes=ground_truth_boxes,
            )

        return {
            "candidates": candidates,
            "candidate_dicts": candidate_dicts,
            "heatmap": heatmap,
            "binary_mask": binary_mask,
            "metrics": metrics,
        }

    def export_candidates_to_json(
        self,
        candidates: Union[List[SatQueryCandidateRecord], List[Dict]],
        output_path: str,
    ) -> str:
        """Export candidates to a formatted, versioned JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if candidates and isinstance(candidates[0], SatQueryCandidateRecord):
            data = [c.model_dump() for c in candidates]
        else:
            data = candidates

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return output_path


def run_pipeline_demo(output_json: Optional[str] = None) -> Dict:
    """Convenience function running a complete end-to-end benchmark demo."""
    # 1. Generate realistic benchmark pair
    scene = generate_benchmark_pair(seed=42, size=(256, 256), num_buildings=3, has_road=True)

    # 2. Fit calibrator on a separate validation set first!
    val_scene = generate_benchmark_pair(seed=101, size=(256, 256), num_buildings=2)
    detector = BaselineChangeDetector()
    val_heatmap, _ = detector.detect_changes(val_scene["img_pre"], val_scene["img_post"])
    val_raw = val_heatmap.ravel()[::16]
    val_gt = (val_scene["mask_gt"].ravel()[::16] > 0).astype(int)

    calibrator = ScoreCalibrator(method="platt")
    calibrator.fit(val_raw, val_gt)

    # 3. Run pipeline
    pipeline = SatQueryPipeline(calibrator=calibrator)
    results = pipeline.process_pair(
        img_pre=scene["img_pre"],
        img_post=scene["img_post"],
        image_pair_id="pair_levir_test_042",
        timestamp="2026-11-16T10:30:00Z",
        ground_truth_mask=scene["mask_gt"],
        ground_truth_boxes=scene["ground_truth_boxes"],
    )

    # 4. Export JSON
    if output_json:
        pipeline.export_candidates_to_json(results["candidates"], output_json)

    return results


if __name__ == "__main__":
    demo_output = os.path.join(os.path.dirname(__file__), "..", "exports", "sample_candidates.json")
    res = run_pipeline_demo(output_json=demo_output)
    print(f"Generated {len(res['candidates'])} candidates.")
    if res["metrics"]:
        print(f"Precision: {res['metrics']['precision']}, Recall: {res['metrics']['recall']}, F1: {res['metrics']['f1_score']}, IoU: {res['metrics']['iou']}")
    print(f"Exported to {demo_output}")
