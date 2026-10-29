from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spitfire_twin_verifier.catalog import COMMANDS

target = ROOT / "reference" / "command_catalog.csv"
with target.open("w", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["id", "command", "operation", "risk"])
    for command_id, spec in sorted(COMMANDS.items()):
        writer.writerow([command_id, spec.text, "write" if spec.writable else "query", spec.risk.value])
print(target)

