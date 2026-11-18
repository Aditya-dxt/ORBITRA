"""Candidate Region Generation for SatQuery.

Turns change detection masks and heatmaps into discrete, identified, georeferenced
candidate change records validated against the SatQueryCandidateRecord schema.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from ..models.classifier import SemanticChangeClassifier
from ..schemas.candidate_record import (
    GeographicCoordinates,
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from .calibration import ScoreCalibrator
from .georeferencing import MissionGeoreferencer


class CandidateGenerator:
    """Generates schema-compliant candidate change records from detection masks."""

    def __init__(
        self,
        georeferencer: Optional[MissionGeoreferencer] = None,
        calibrator: Optional[ScoreCalibrator] = None,
        classifier: Optional[SemanticChangeClassifier] = None,
        min_pixel_area: int = 25,
        default_schema_version: str = "v1.0.0",
    ):
        """
        Args:
            georeferencer: Instance of MissionGeoreferencer for coordinate transforms.
            calibrator: Fitted ScoreCalibrator for probability calibration.
            classifier: SemanticChangeClassifier for patch classification.
            min_pixel_area: Minimum connected component area in pixels.
            default_schema_version: Schema version string.
        """
        self.georeferencer = georeferencer or MissionGeoreferencer()
        self.calibrator = calibrator or ScoreCalibrator()
        self.classifier = classifier or SemanticChangeClassifier()
        self.min_pixel_area = min_pixel_area
        self.schema_version = default_schema_version

    def generate_candidates(
        self,
        img_pre: np.ndarray,
        img_post: np.ndarray,
        binary_mask: np.ndarray,
        heatmap: np.ndarray,
        image_pair_id: str = "pair_levir_001",
        timestamp: Optional[str] = None,
        dataset_name: str = "levir",
    ) -> List[SatQueryCandidateRecord]:
        """Extract candidate change records from detection outputs.
        
        Args:
            img_pre: Pre-change RGB uint8 image.
            img_post: Post-change RGB uint8 image.
            binary_mask: Binary change mask uint8 (H, W) where change > 0.
            heatmap: Continuous change intensity heatmap float32 (H, W) in [0, 1].
            image_pair_id: Identifier of the bi-temporal image pair.
            timestamp: ISO-8601 UTC timestamp string. Defaults to current UTC time.
            dataset_name: Dataset prefix for candidate ID generation.
            
        Returns:
            List of strictly validated SatQueryCandidateRecord instances.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Find external contours of change regions
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates: List[SatQueryCandidateRecord] = []
        candidate_idx = 1

        for contour in contours:
            area_px = cv2.contourArea(contour)
            if area_px < self.min_pixel_area:
                continue

            # Bounding box in pixel coordinates [xmin, ymin, xmax, ymax]
            bx, by, bw, bh = cv2.boundingRect(contour)
            bbox = [int(bx), int(by), int(bx + bw), int(by + bh)]

            # Extract patch crops
            patch_pre = img_pre[by : by + bh, bx : bx + bw]
            patch_post = img_post[by : by + bh, bx : bx + bw]

            # 1. Semantic classification
            predicted_change, _ = self.classifier.classify_patch(patch_pre, patch_post)

            # 2. Score pooling over candidate region
            region_mask = np.zeros_like(heatmap, dtype=np.uint8)
            cv2.drawContours(region_mask, [contour], -1, 1, thickness=-1)
            raw_region_score = float(np.mean(heatmap[region_mask > 0])) if np.sum(region_mask) > 0 else 0.50

            # 3. Calibrated confidence and uncertainty
            confidence, uncertainty = self.calibrator.calibrate_candidate(raw_region_score)

            # 4. Georeferencing
            region_dict = self.georeferencer.create_region_geometry(bbox)
            region_geom = RegionGeometry(
                crs=region_dict["crs"],
                local_grid=LocalGridCoordinates(**region_dict["local_grid"]),
                coordinates=GeographicCoordinates(**region_dict["coordinates"]) if "coordinates" in region_dict else None,
                bbox_pixels=bbox,
            )

            # 5. Candidate ID construction
            cand_id = f"cand_sq_{dataset_name}_{candidate_idx:03d}"
            candidate_idx += 1

            record = SatQueryCandidateRecord(
                schema_version=self.schema_version,
                candidate_id=cand_id,
                image_pair_id=image_pair_id,
                timestamp=timestamp,
                predicted_change=predicted_change,
                confidence=confidence,
                uncertainty=uncertainty,
                region=region_geom,
            )
            candidates.append(record)

        return candidates
