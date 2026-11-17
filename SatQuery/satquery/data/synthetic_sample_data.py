"""Reproducible synthetic benchmark scene generator for SatQuery.

Generates realistic bi-temporal satellite image pairs with Ground Truth change masks
for test suites, standalone demos, and calibration experiments without external data dependencies.
"""

from typing import Dict, List, Tuple
import cv2
import numpy as np


def generate_benchmark_pair(
    seed: int = 42,
    size: Tuple[int, int] = (256, 256),
    num_buildings: int = 3,
    has_road: bool = True,
    has_clearing: bool = True,
) -> Dict[str, np.ndarray]:
    """Generate a realistic bitemporal satellite image pair and true change mask.
    
    Returns:
        Dict with keys:
            'img_pre': Pre-change RGB uint8 image (H, W, 3)
            'img_post': Post-change RGB uint8 image (H, W, 3)
            'mask_gt': Ground truth binary change mask (H, W) where change is 255
            'ground_truth_boxes': List of [xmin, ymin, xmax, ymax]
            'change_classes': List of ground truth change class names
    """
    rng = np.random.RandomState(seed)
    h, w = size

    # 1. Base terrain (vegetation and soil texture)
    base_terrain = np.zeros((h, w, 3), dtype=np.uint8)
    base_terrain[:, :, 0] = rng.randint(45, 65, size=(h, w), dtype=np.uint8)   # Red
    base_terrain[:, :, 1] = rng.randint(90, 120, size=(h, w), dtype=np.uint8)  # Green (vegetation)
    base_terrain[:, :, 2] = rng.randint(35, 55, size=(h, w), dtype=np.uint8)   # Blue

    # Add gentle spatial gradient (field patterns)
    x_coords, y_coords = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    gradient = (np.sin(x_coords * 6.0) * 15 + np.cos(y_coords * 4.0) * 15).astype(np.int16)
    base_terrain = np.clip(base_terrain.astype(np.int16) + gradient[:, :, None], 0, 255).astype(np.uint8)

    img_pre = base_terrain.copy()
    img_post = base_terrain.copy()
    mask_gt = np.zeros((h, w), dtype=np.uint8)
    gt_boxes = []
    change_classes = []

    # 2. Add Existing unchanged features (existing road or old building)
    cv2.line(img_pre, (0, int(h * 0.8)), (w, int(h * 0.85)), (70, 70, 75), thickness=4)
    cv2.line(img_post, (0, int(h * 0.8)), (w, int(h * 0.85)), (70, 70, 75), thickness=4)

    # 3. Add NEW Building Constructions (in Post only)
    building_coords = [
        (40, 40, 75, 75),     # Box 1: [xmin, ymin, xmax, ymax]
        (130, 60, 175, 100),  # Box 2: [xmin, ymin, xmax, ymax]
        (160, 160, 210, 215), # Box 3: [xmin, ymin, xmax, ymax]
    ][:num_buildings]

    roof_colors = [(180, 70, 60), (200, 200, 210), (160, 150, 140)]

    for idx, (bx1, by1, bx2, by2) in enumerate(building_coords):
        color = roof_colors[idx % len(roof_colors)]
        # Draw on post image
        cv2.rectangle(img_post, (bx1, by1), (bx2, by2), color, -1)
        # Add a subtle roof shadow
        cv2.rectangle(img_post, (bx2, by1 + 4), (bx2 + 6, by2 + 6), (30, 35, 30), -1)
        # Mark on ground truth mask
        cv2.rectangle(mask_gt, (bx1, by1), (bx2, by2), 255, -1)
        gt_boxes.append([bx1, by1, bx2, by2])
        change_classes.append("urban_building_construction")

    # 4. Add NEW Road Works / Infrastructure (if requested)
    if has_road:
        rx1, ry1, rx2, ry2 = 80, 120, 240, 135
        cv2.rectangle(img_post, (rx1, ry1), (rx2, ry2), (140, 140, 145), -1)
        cv2.rectangle(mask_gt, (rx1, ry1), (rx2, ry2), 255, -1)
        gt_boxes.append([rx1, ry1, rx2, ry2])
        change_classes.append("road_infrastructure")

    # 5. Add Vegetation Clearing (if requested)
    if has_clearing:
        cx1, cy1, cx2, cy2 = 25, 150, 70, 200
        # Cleared ground turns brownish/sandy
        cv2.rectangle(img_post, (cx1, cy1), (cx2, cy2), (165, 140, 105), -1)
        cv2.rectangle(mask_gt, (cx1, cy1), (cx2, cy2), 255, -1)
        gt_boxes.append([cx1, cy1, cx2, cy2])
        change_classes.append("vegetation_clearing")

    # 6. Apply realistic seasonal illumination shift and sensor noise
    # Post image has slight seasonal brightness and sun angle shift
    noise_pre = rng.normal(0, 3.0, size=(h, w, 3)).astype(np.int16)
    noise_post = rng.normal(0, 3.5, size=(h, w, 3)).astype(np.int16)

    # Slight seasonal grass hue shift
    post_shifted = img_post.astype(np.int16)
    post_shifted[:, :, 1] = np.clip(post_shifted[:, :, 1] - 4, 0, 255) # slightly drier grass
    post_shifted[:, :, 0] = np.clip(post_shifted[:, :, 0] + 3, 0, 255) # warmer sunlight

    img_pre_final = np.clip(img_pre.astype(np.int16) + noise_pre, 0, 255).astype(np.uint8)
    img_post_final = np.clip(post_shifted + noise_post, 0, 255).astype(np.uint8)

    return {
        "img_pre": img_pre_final,
        "img_post": img_post_final,
        "mask_gt": mask_gt,
        "ground_truth_boxes": gt_boxes,
        "change_classes": change_classes,
    }
