"""Unit tests for baseline change detection and candidate region generation."""

import unittest
import numpy as np

from SatQuery.satquery.data.synthetic_sample_data import generate_benchmark_pair
from SatQuery.satquery.evaluation.metrics import VisionEvaluator, compute_pixel_metrics
from SatQuery.satquery.vision.candidate_generator import CandidateGenerator
from SatQuery.satquery.vision.detector import BaselineChangeDetector


class TestDetectorAndCandidateGeneration(unittest.TestCase):
    """Verifies baseline detector, candidate extraction, and vision metrics."""

    def setUp(self):
        self.scene = generate_benchmark_pair(
            seed=42, size=(256, 256), num_buildings=3, has_road=True, has_clearing=True
        )
        self.detector = BaselineChangeDetector(threshold=0.35, min_contour_area=25)
        self.candidate_gen = CandidateGenerator(min_pixel_area=25)
        self.evaluator = VisionEvaluator(tau_iou=0.5)

    def test_detector_output_shapes_and_ranges(self):
        heatmap, mask = self.detector.detect_changes(
            self.scene["img_pre"], self.scene["img_post"]
        )
        self.assertEqual(heatmap.shape, (256, 256))
        self.assertEqual(mask.shape, (256, 256))
        self.assertGreaterEqual(float(np.min(heatmap)), 0.0)
        self.assertLessEqual(float(np.max(heatmap)), 1.0)
        self.assertIn(mask.dtype, [np.uint8])

    def test_detector_evaluation_metrics(self):
        heatmap, mask = self.detector.detect_changes(
            self.scene["img_pre"], self.scene["img_post"]
        )
        metrics = compute_pixel_metrics(mask, self.scene["mask_gt"])

        self.assertGreater(metrics["precision"], 0.70)
        self.assertGreater(metrics["recall"], 0.40)
        self.assertGreater(metrics["f1_score"], 0.50)
        self.assertGreater(metrics["iou"], 0.35)

    def test_candidate_generation_and_region_extraction(self):
        heatmap, mask = self.detector.detect_changes(
            self.scene["img_pre"], self.scene["img_post"]
        )
        candidates = self.candidate_gen.generate_candidates(
            img_pre=self.scene["img_pre"],
            img_post=self.scene["img_post"],
            binary_mask=mask,
            heatmap=heatmap,
            image_pair_id="pair_benchmark_001",
            timestamp="2026-11-16T12:00:00Z",
        )

        self.assertGreater(len(candidates), 0)
        first = candidates[0]
        self.assertTrue(first.candidate_id.startswith("cand_sq_"))
        self.assertGreaterEqual(first.confidence, 0.0)
        self.assertLessEqual(first.confidence, 1.0)
        self.assertGreaterEqual(first.uncertainty, 0.0)
        self.assertLessEqual(first.uncertainty, 1.0)
        self.assertIsNotNone(first.region.local_grid)
        self.assertGreater(first.region.local_grid.x_meters, 0.0)

    def test_no_change_scene_produces_zero_or_low_candidates(self):
        """Identical pre/post scenes should produce no change candidates."""
        img = self.scene["img_pre"]
        heatmap, mask = self.detector.detect_changes(img, img)
        candidates = self.candidate_gen.generate_candidates(
            img_pre=img,
            img_post=img,
            binary_mask=mask,
            heatmap=heatmap,
            image_pair_id="pair_identical_001",
            timestamp="2026-11-16T12:00:00Z",
        )
        self.assertEqual(len(candidates), 0)


if __name__ == "__main__":
    unittest.main()
