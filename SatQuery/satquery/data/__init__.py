"""Data package for SatQuery."""

from .dataset import ChangeDetectionDataset
from .synthetic_sample_data import generate_benchmark_pair
from .india_satellite_data import INDIAN_MISSION_ZONES, IndiaSatelliteDataLoader
from .image_resolver import ImagePairResolver, ResolvedImagePair
from .mission_gallery import MissionGalleryGenerator, compute_shannon_entropy

__all__ = [
    "ChangeDetectionDataset",
    "generate_benchmark_pair",
    "INDIAN_MISSION_ZONES",
    "IndiaSatelliteDataLoader",
    "ImagePairResolver",
    "ResolvedImagePair",
    "MissionGalleryGenerator",
    "compute_shannon_entropy",
]
