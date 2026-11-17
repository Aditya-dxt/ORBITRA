"""Generates sample satellite image pairs and qualitative visual overlay assets."""

import os
import cv2
import numpy as np
from PIL import Image

from .synthetic_sample_data import generate_benchmark_pair
from ..vision.detector import BaselineChangeDetector
from ..vision.georeferencing import MissionGeoreferencer
from ..vision.candidate_generator import CandidateGenerator


def generate_sample_assets():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sample_pairs_dir = os.path.join(base_dir, "data", "sample_pairs")
    vis_dir = os.path.join(base_dir, "exports", "visualizations")
    os.makedirs(sample_pairs_dir, exist_ok=True)
    os.makedirs(vis_dir, exist_ok=True)

    # 1. Generate 3 representative scenes
    scenes = [
        ("scene_levir_042", 42, 3, True, True),
        ("scene_levir_088", 88, 2, False, True),
        ("scene_levir_105", 105, 4, True, False),
    ]

    detector = BaselineChangeDetector()
    candidate_gen = CandidateGenerator()

    for name, seed, n_bld, road, clear in scenes:
        scene = generate_benchmark_pair(seed=seed, size=(256, 256), num_buildings=n_bld, has_road=road, has_clearing=clear)
        
        # Save raw images
        path_pre = os.path.join(sample_pairs_dir, f"{name}_pre.png")
        path_post = os.path.join(sample_pairs_dir, f"{name}_post.png")
        path_gt = os.path.join(sample_pairs_dir, f"{name}_gt_mask.png")

        Image.fromarray(scene["img_pre"]).save(path_pre)
        Image.fromarray(scene["img_post"]).save(path_post)
        Image.fromarray(scene["mask_gt"]).save(path_gt)

        # 2. Run detector and create visual comparison montage
        heatmap, mask = detector.detect_changes(scene["img_pre"], scene["img_post"])
        candidates = candidate_gen.generate_candidates(
            img_pre=scene["img_pre"],
            img_post=scene["img_post"],
            binary_mask=mask,
            heatmap=heatmap,
            image_pair_id=f"pair_{name}",
        )

        # Create annotated overlay on post image
        annotated = scene["img_post"].copy()
        for cand in candidates:
            if cand.region.bbox_pixels:
                x1, y1, x2, y2 = cand.region.bbox_pixels
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 60, 0), 2)
                label = f"{cand.candidate_id} p={cand.confidence:.2f} u={cand.uncertainty:.2f}"
                cv2.putText(
                    annotated, label, (x1, max(y1 - 4, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1
                )

        # Convert heatmap to false color (JET)
        heatmap_uint8 = (heatmap * 255).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
        heatmap_rgb = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

        # Convert binary mask to RGB
        mask_rgb = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)

        # Create 1x4 horizontal montage: Pre | Post | Heatmap | Detections
        h, w = scene["img_pre"].shape[:2]
        montage = np.zeros((h, w * 4, 3), dtype=np.uint8)
        montage[:, :w] = scene["img_pre"]
        montage[:, w : w * 2] = scene["img_post"]
        montage[:, w * 2 : w * 3] = heatmap_rgb
        montage[:, w * 3 :] = annotated

        # Add titles
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(montage, "Pre-Change (T1)", (10, 20), font, 0.5, (255, 255, 255), 1)
        cv2.putText(montage, "Post-Change (T2)", (w + 10, 20), font, 0.5, (255, 255, 255), 1)
        cv2.putText(montage, "Heatmap", (w * 2 + 10, 20), font, 0.5, (255, 255, 255), 1)
        cv2.putText(montage, "Detected Candidates", (w * 3 + 10, 20), font, 0.5, (0, 255, 255), 1)

        vis_path = os.path.join(vis_dir, f"{name}_montage.png")
        Image.fromarray(montage).save(vis_path)

    print("Sample assets and visual montages generated successfully.")


if __name__ == "__main__":
    generate_sample_assets()
