"""All regression tests use simulators or loopback, including local pytest runs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ci_guard import install

install()
