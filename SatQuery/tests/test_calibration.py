"""Unit tests for confidence calibration and uncertainty quantification."""

import unittest
import numpy as np

from SatQuery.satquery.vision.calibration import (
    ScoreCalibrator,
    binary_entropy_uncertainty,
)


class TestCalibrationAndUncertainty(unittest.TestCase):
    """Verifies calibration fitting on val, evaluation on held-out test, and entropy uncertainty."""

    def test_binary_entropy_uncertainty_properties(self):
        # Maximum uncertainty at p = 0.5
        u_mid = binary_entropy_uncertainty(0.5)
        self.assertAlmostEqual(u_mid, 1.0, places=4)

        # Minimum uncertainty at extreme probabilities
        u_zero = binary_entropy_uncertainty(0.0)
        self.assertAlmostEqual(u_zero, 0.0, places=4)

        u_one = binary_entropy_uncertainty(1.0)
        self.assertAlmostEqual(u_one, 0.0, places=4)

        # Monotonic descent away from 0.5
        self.assertGreater(binary_entropy_uncertainty(0.5), binary_entropy_uncertainty(0.7))
        self.assertGreater(binary_entropy_uncertainty(0.7), binary_entropy_uncertainty(0.95))

    def test_calibration_on_held_out_test_split(self):
        """Fits calibration on val split, and computes ECE & Brier score on held-out test split."""
        rng = np.random.RandomState(42)

        # 1. Validation Split (used strictly to fit calibration parameters)
        n_val = 400
        val_true_p = rng.uniform(0.1, 0.9, n_val)
        val_labels = (rng.uniform(0, 1, n_val) < val_true_p).astype(int)
        # Uncalibrated scores with systematic over-confidence distortion
        val_raw_scores = np.clip(val_true_p**0.5, 0.0, 1.0)

        calibrator = ScoreCalibrator(method="platt")
        calibrator.fit(val_raw_scores, val_labels)
        self.assertTrue(calibrator.is_fitted)

        # 2. Held-Out Test Split (never seen during calibration fitting)
        n_test = 500
        test_true_p = rng.uniform(0.1, 0.9, n_test)
        test_labels = (rng.uniform(0, 1, n_test) < test_true_p).astype(int)
        test_raw_scores = np.clip(test_true_p**0.5, 0.0, 1.0)

        # Uncalibrated baseline metrics on test split
        raw_eval = ScoreCalibrator.evaluate_calibration(test_raw_scores, test_labels, num_bins=10)

        # Calibrated metrics on test split
        test_cal_probs = calibrator.predict_probability(test_raw_scores)
        cal_eval = ScoreCalibrator.evaluate_calibration(test_cal_probs, test_labels, num_bins=10)

        # Verify expected metric properties on held-out data
        self.assertIn("ece", cal_eval)
        self.assertIn("brier_score", cal_eval)
        self.assertIn("mce", cal_eval)
        self.assertEqual(cal_eval["num_samples"], n_test)

        # Calibration must achieve lower Brier score than uncalibrated raw scores on held-out test data
        self.assertLess(cal_eval["brier_score"], raw_eval["brier_score"])
        self.assertLess(cal_eval["ece"], raw_eval["ece"])


if __name__ == "__main__":
    unittest.main()
