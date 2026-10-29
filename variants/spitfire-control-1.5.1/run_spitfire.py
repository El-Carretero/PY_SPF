#!/usr/bin/env python3
"""Run directly from a source checkout without installing the package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from spitfire_control.app import main


if __name__ == "__main__":
    raise SystemExit(main())

