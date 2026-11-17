"""Checkpoint Loader and Inspector for SatQuery.

Loads and audits model weights from PyTorch checkpoint files (*.pth)
with or without PyTorch installed in the active environment.
Uses standard library zipfile and pickle streams to parse state_dict,
training history, and validation metrics safely.
"""

import io
import os
import pickle
import zipfile
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class _TorchZipUnpickler(pickle.Unpickler):
    """Safe unpickler for PyTorch checkpoint metadata without requiring torch."""

    def __init__(self, f, zfile=None, prefix=""):
        super().__init__(f)
        self.zfile = zfile
        self.prefix = prefix

    def find_class(self, module: str, name: str) -> Any:
        if "collections" in module and name == "OrderedDict":
            import collections
            return collections.OrderedDict
        if module == "torch._utils":
            return lambda *args: args
        if module == "torch" and "Storage" in name:
            return lambda *args: (name, args)
        return lambda *args, **kwargs: (module, name, args, kwargs)

    def persistent_load(self, pid: Any) -> Any:
        return pid


def find_checkpoint(custom_path: Optional[str] = None) -> Optional[str]:
    """Locate the best Siamese model checkpoint file.

    Checks:
    1. custom_path (if provided and exists)
    2. SatQuery/models/checkpoints/best_siamese_model.pth
    3. C:\\Users\\adity\\Downloads\\best_siamese_model.pth
    4. Current working directory ./best_siamese_model.pth
    """
    candidates = []
    if custom_path:
        candidates.append(custom_path)

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.extend([
        os.path.join(base_dir, "models", "checkpoints", "best_siamese_model.pth"),
        os.path.join(os.path.expanduser("~"), "Downloads", "best_siamese_model.pth"),
        os.path.join(r"C:\Users\adity\Downloads", "best_siamese_model.pth"),
        os.path.join(".", "best_siamese_model.pth"),
    ])

    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def inspect_checkpoint(checkpoint_path: str) -> Dict[str, Any]:
    """Inspect checkpoint file and return structured training and architecture metadata.

    Returns:
        Dict with keys:
            - 'epoch': int (training epochs completed)
            - 'best_f1': float (peak validation F1 score)
            - 'val_iou': float (peak validation IoU score)
            - 'val_loss': float (validation loss)
            - 'num_parameters': int (number of parameter tensors in state_dict)
            - 'history': Dict[str, List[float]] (loss/IoU/F1 progression over epochs)
            - 'architecture': str (identifying model family)
            - 'size_mb': float (file size in MB)
    """
    if not os.path.isfile(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint not found at: {checkpoint_path}")

    size_mb = os.path.getsize(checkpoint_path) / (1024 * 1024)

    if not zipfile.is_zipfile(checkpoint_path):
        return {
            "path": checkpoint_path,
            "size_mb": round(size_mb, 2),
            "format": "legacy_pickle",
            "architecture": "SiameseResNet34",
        }

    with zipfile.ZipFile(checkpoint_path, "r") as z:
        # Find data.pkl
        pkl_entry = None
        prefix = ""
        for name in z.namelist():
            if name.endswith("data.pkl"):
                pkl_entry = name
                prefix = name[:-len("data.pkl")]
                break

        if not pkl_entry:
            raise ValueError(f"Invalid PyTorch archive {checkpoint_path}: data.pkl not found.")

        with z.open(pkl_entry) as f:
            up = _TorchZipUnpickler(f, z, prefix)
            obj = up.load()

    epoch = obj.get("epoch", 0)
    best_f1 = float(obj.get("best_f1", 0.0))
    history = obj.get("history", {})
    state_dict = obj.get("model_state_dict", {})

    val_iou = history.get("val_iou", [-1.0])[-1] if history.get("val_iou") else 0.0
    val_loss = history.get("val_loss", [-1.0])[-1] if history.get("val_loss") else 0.0

    return {
        "path": checkpoint_path,
        "size_mb": round(size_mb, 2),
        "epoch": epoch,
        "best_f1": round(best_f1, 4),
        "val_iou": round(float(val_iou), 4),
        "val_loss": round(float(val_loss), 4),
        "num_parameters": len(state_dict),
        "history": history,
        "architecture": "SiameseResNet34-CBAM-Attention",
    }
