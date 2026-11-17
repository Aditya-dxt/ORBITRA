"""Data package for SatQuery."""

from .dataset import ChangeDetectionDataset
from .synthetic_sample_data import generate_benchmark_pair
from .india_satellite_data import INDIAN_MISSION_ZONES, IndiaSatelliteDataLoader

__all__ = [
    "ChangeDetectionDataset",
    "generate_benchmark_pair",
    "INDIAN_MISSION_ZONES",
    "IndiaSatelliteDataLoader",
]
