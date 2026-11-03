#!/usr/bin/env python3
"""Run the validator from the source ZIP without installing the package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from spitfire_control.validation import main

if __name__ == "__main__":
    raise SystemExit(main())
