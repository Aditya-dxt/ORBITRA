"""Convenience entry point for the ARES matched-budget policy benchmark."""

from pathlib import Path
import sys

ARES_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ARES_ROOT))

from ares.simulation.benchmark import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
