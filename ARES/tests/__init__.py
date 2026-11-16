"""ARES Test Suite setup and path resolution."""

import sys
from pathlib import Path

# Automatically add ARES root to sys.path so tests can be run from workspace root
ares_root = Path(__file__).resolve().parent.parent
if str(ares_root) not in sys.path:
    sys.path.insert(0, str(ares_root))
