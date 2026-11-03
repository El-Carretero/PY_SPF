"""Source-tree launcher; double-click Start-SpitfireTwinVerifier.bat on Windows."""

from pathlib import Path
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from spitfire_twin_verifier.cli import main

raise SystemExit(main())
