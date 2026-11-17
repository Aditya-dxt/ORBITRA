"""Unit tests for Deep Siamese Model integration and checkpoint audit."""

import os
import unittest
import numpy as np

from SatQuery.satquery.models.checkpoint_loader import find_checkpoint, inspect_checkpoint
from SatQuery.satquery.models.siamese_unet import TORCH_AVAILABLE, SiameseUNetAttention
from SatQuery.satquery.vision.deep_detector import DeepSiameseChangeDetector
from SatQuery.satquery.vision.candidate_generator import CandidateGenerator
from SatQuery.satquery.schemas.candidate_record import SatQueryCandidateRecord


class TestDeepSiameseModel(unittest.TestCase):
    """Test suite verifying the deep Siamese ResNet-34 model checkpoint and detector."""

    def test_checkpoint_discovery_and_metadata(self):
        """Verify checkpoint loader locates best_siamese_model.pth and parses metadata."""
        ckpt_path = find_checkpoint()
        self.assertIsNotNone(ckpt_path, "Checkpoint best_siamese_model.pth should be discovered")
        self.assertTrue(os.path.isfile(ckpt_path), f"Checkpoint must exist at {ckpt_path}")

        info = inspect_checkpoint(ckpt_path)
        self.assertEqual(info["epoch"], 35, "Model must have been trained for 35 epochs")
        self.assertAlmostEqual(info["best_f1"], 0.8475, places=3, msg="Peak validation F1 must be ~84.75%")
        self.assertAlmostEqual(info["val_iou"], 0.7354, places=3, msg="Peak validation IoU must be ~73.54%")
        self.assertEqual(info["num_parameters"], 315, "Model state_dict must contain 315 parameter tensors")
        self.assertEqual(info["architecture"], "SiameseResNet34-CBAM-Attention")

    def test_deep_detector_initialization(self):
        """Verify DeepSiameseChangeDetector initializes cleanly with diagnostic info."""
        detector = DeepSiameseChangeDetector(threshold=0.40)
        info = detector.get_model_info()
        self.assertIn("mode", info)
        self.assertIn("threshold", info)
        self.assertEqual(info["threshold"], 0.40)
        self.assertTrue(info["checkpoint_found"])

    def test_deep_detector_inference(self):
        """Verify detect_changes yields continuous heatmap in [0, 1] and binary mask in {0, 255}."""
        detector = DeepSiameseChangeDetector(threshold=0.40)
        h, w = 128, 128
        pre = np.zeros((h, w, 3), dtype=np.uint8)
        post = np.zeros((h, w, 3), dtype=np.uint8)
        # Add synthetic change (building addition)
        post[30:70, 30:70, :] = 220

        heatmap, binary_mask = detector.detect_changes(pre, post)

        self.assertEqual(heatmap.shape, (h, w))
        self.assertEqual(binary_mask.shape, (h, w))
        self.assertGreaterEqual(float(heatmap.min()), 0.0)
        self.assertLessEqual(float(heatmap.max()), 1.0)
        # Change region should exhibit high probability
        change_region_prob = heatmap[40:60, 40:60].mean()
        background_prob = heatmap[5:20, 5:20].mean()
        self.assertGreater(change_region_prob, background_prob)

    def test_candidate_generation_with_deep_detector(self):
        """Verify end-to-end generation of schema-compliant candidate records."""
        detector = DeepSiameseChangeDetector(threshold=0.35)
        generator = CandidateGenerator(min_pixel_area=10)

        h, w = 256, 256
        pre = np.ones((h, w, 3), dtype=np.uint8) * 100
        post = np.ones((h, w, 3), dtype=np.uint8) * 100
        # Add two distinct building additions
        post[40:80, 40:80] = 230
        post[140:190, 140:190] = 240

        heatmap, binary_mask = detector.detect_changes(pre, post)
        candidates = generator.generate_candidates(
            img_pre=pre,
            img_post=post,
            binary_mask=binary_mask,
            heatmap=heatmap,
            image_pair_id="test_deep_pair_001",
        )

        self.assertGreaterEqual(len(candidates), 1, "Should detect at least 1 candidate change region")
        for cand in candidates:
            self.assertIsInstance(cand, SatQueryCandidateRecord)
            self.assertGreaterEqual(cand.confidence, 0.0)
            self.assertLessEqual(cand.confidence, 1.0)
            self.assertGreaterEqual(cand.uncertainty, 0.0)
            self.assertLessEqual(cand.uncertainty, 1.0)
            self.assertEqual(cand.schema_version, "v1.0.0-provisional")


if __name__ == "__main__":
    unittest.main()
