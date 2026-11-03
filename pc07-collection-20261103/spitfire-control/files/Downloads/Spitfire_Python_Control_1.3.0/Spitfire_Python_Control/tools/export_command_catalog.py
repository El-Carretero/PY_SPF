#!/usr/bin/env python3
"""Regenerate docs/command_catalog.csv from the authoritative Python table."""

from pathlib import Path
import csv
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from spitfire_control.commands import COMMANDS


def main() -> None:
    target = PROJECT / "docs" / "command_catalog.csv"
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("id", "command", "direction", "risk", "description"))
        for command_id, spec in sorted(COMMANDS.items()):
            writer.writerow((
                command_id,
                spec.text,
                "write" if spec.writable else "query",
                spec.risk.value,
                spec.description,
            ))


if __name__ == "__main__":
    main()

