"""Confidence Calibration and Uncertainty Quantification for SatQuery.

Computes:
1. Calibrated candidate probability p_i in [0.0, 1.0] using Platt Scaling / Logistic Regression
   or Temperature Scaling.
2. Normalized Binary Shannon Entropy u_i in [0.0, 1.0]:
   u_i = - [ p_i * log2(p_i) + (1 - p_i) * log2(1 - p_i) ]
3. Empirical calibration metrics evaluated strictly on HELD-OUT data:
   - Expected Calibration Error (ECE)
   - Brier Score: (1/N) * sum((p_i - y_i)^2)
   - Maximum Calibration Error (MCE)
"""

import math
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from sklearn.linear_model import LogisticRegression


def binary_entropy_uncertainty(p: float, eps: float = 1e-7) -> float:
    """Calculate normalized binary Shannon entropy in [0.0, 1.0].
    
    Formula:
        u = - [ p * log2(p) + (1 - p) * log2(1 - p) ]
    
    Properties:
        - When p = 0.5 (maximum ambiguity), u = 1.0
        - When p -> 0.0 or p -> 1.0 (maximum confidence), u -> 0.0
    """
    p_clipped = np.clip(p, eps, 1.0 - eps)
    entropy = - (p_clipped * np.log2(p_clipped) + (1.0 - p_clipped) * np.log2(1.0 - p_clipped))
    return float(np.clip(entropy, 0.0, 1.0))


class ScoreCalibrator:
    """Calibrator for vision detector change scores.
    
    Fits calibration parameters on a validation split, and evaluates calibration metrics
    strictly on a separate held-out test split to ensure honest assessment.
    """

    def __init__(self, method: str = "platt"):
        """
        Args:
            method: 'platt' (Platt scaling / logistic sigmoid) or 'temperature' (Temperature scaling).
        """
        self.method = method
        self.is_fitted = False
        self._scaler = None
        self.temperature = 1.0

    def fit(self, raw_scores: np.ndarray, ground_truth: np.ndarray) -> "ScoreCalibrator":
        """Fit calibration on the VALIDATION split.
        
        Args:
            raw_scores: 1D array of uncalibrated detector change scores in [0, 1] or logits.
            ground_truth: 1D array of binary true change labels in {0, 1}.
        """
        raw_scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1, 1)
        ground_truth = np.asarray(ground_truth, dtype=np.int32).ravel()

        if len(np.unique(ground_truth)) < 2:
            # Degenerate case fallback
            self.is_fitted = True
            return self

        if self.method == "platt":
            self._scaler = LogisticRegression(solver="lbfgs", max_iter=200, C=1.0)
            self._scaler.fit(raw_scores, ground_truth)
        elif self.method == "temperature":
            # Simple grid search for optimal temperature minimizing NLL on validation split
            temps = np.linspace(0.2, 5.0, 49)
            best_nll = float("inf")
            best_t = 1.0
            eps = 1e-7
            for t in temps:
                scaled_probs = 1.0 / (1.0 + np.exp(-raw_scores / t))
                scaled_probs = np.clip(scaled_probs, eps, 1.0 - eps)
                nll = -np.mean(ground_truth * np.log(scaled_probs) + (1 - ground_truth) * np.log(1 - scaled_probs))
                if nll < best_nll:
                    best_nll = nll
                    best_t = t
            self.temperature = float(best_t)

        self.is_fitted = True
        return self

    def predict_probability(self, raw_score: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """Convert raw detector score into calibrated probability p in [0.0, 1.0]."""
        scalar_input = np.isscalar(raw_score)
        scores = np.atleast_1d(raw_score).astype(np.float64)

        if not self.is_fitted:
            # Uncalibrated baseline pass-through with clipping
            calibrated = np.clip(scores, 0.0, 1.0)
        elif self.method == "platt" and self._scaler is not None:
            probs = self._scaler.predict_proba(scores.reshape(-1, 1))[:, 1]
            calibrated = np.clip(probs, 0.0, 1.0)
        elif self.method == "temperature":
            calibrated = 1.0 / (1.0 + np.exp(-scores / self.temperature))
            calibrated = np.clip(calibrated, 0.0, 1.0)
        else:
            calibrated = np.clip(scores, 0.0, 1.0)

        return float(calibrated[0]) if scalar_input else calibrated

    def calibrate_candidate(self, raw_score: float) -> Tuple[float, float]:
        """Convenience method returning (calibrated_confidence, uncertainty)."""
        p = float(self.predict_probability(raw_score))
        u = binary_entropy_uncertainty(p)
        return round(p, 4), round(u, 4)

    @staticmethod
    def evaluate_calibration(
        probabilities: np.ndarray,
        ground_truth: np.ndarray,
        num_bins: int = 10
    ) -> Dict[str, float]:
        """Evaluate calibration quality on HELD-OUT data (ECE, MCE, Brier score).
        
        Args:
            probabilities: Calibrated probabilities p_i in [0.0, 1.0] from held-out set.
            ground_truth: Ground truth binary labels y_i in {0, 1} from held-out set.
            num_bins: Number of equal-width probability bins.
            
        Returns:
            Dict containing 'ece', 'mce', 'brier_score', and 'num_samples'.
        """
        probs = np.asarray(probabilities, dtype=np.float64).ravel()
        labels = np.asarray(ground_truth, dtype=np.float64).ravel()
        n = len(probs)
        if n == 0:
            return {"ece": 0.0, "mce": 0.0, "brier_score": 0.0, "num_samples": 0}

        # Brier Score: MSE between predicted probability and binary outcome
        brier_score = float(np.mean((probs - labels) ** 2))

        # Expected Calibration Error (ECE) and Maximum Calibration Error (MCE)
        bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
        ece = 0.0
        mce = 0.0

        for i in range(num_bins):
            bin_lower = bin_edges[i]
            bin_upper = bin_edges[i + 1]

            if i == num_bins - 1:
                in_bin = (probs >= bin_lower) & (probs <= bin_upper)
            else:
                in_bin = (probs >= bin_lower) & (probs < bin_upper)

            bin_count = np.sum(in_bin)
            if bin_count > 0:
                bin_acc = np.mean(labels[in_bin])
                bin_conf = np.mean(probs[in_bin])
                gap = abs(bin_acc - bin_conf)
                ece += (bin_count / n) * gap
                mce = max(mce, gap)

        return {
            "ece": round(float(ece), 4),
            "mce": round(float(mce), 4),
            "brier_score": round(float(brier_score), 4),
            "num_samples": n,
        }
