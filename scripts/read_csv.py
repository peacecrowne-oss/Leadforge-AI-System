#!/usr/bin/env python3
"""Quick read-and-print for apollo-leads.csv.

Uses only stdlib. No existing files are modified.

Usage:
    python scripts/read_csv.py
"""
import csv

PATH = "C:/AI PROJECTS1/INTERNSHIP/LeadForge-AI-System/apollo-leads.csv"


def read_csv(path: str) -> list[dict]:
    """Read CSV with UTF-8 / latin-1 fallback. Strips whitespace from all keys and values."""
    for encoding in ("utf-8", "latin-1"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                rows = []
                for row in reader:
                    rows.append({k.strip(): v.strip() for k, v in row.items() if k})
            print(f"[read_csv] Opened with encoding: {encoding}")
            return rows
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode {path} with utf-8 or latin-1")


def main() -> None:
    rows = read_csv(PATH)

    print(f"\nTotal rows : {len(rows)}")
    print(f"Columns    : {list(rows[0].keys()) if rows else '(empty)'}")
    print()

    for i, row in enumerate(rows[:3], start=1):
        print(f"-- Row {i} ----------------------------------")
        for key, val in row.items():
            print(f"  {key:<30} {val}")

    if len(rows) > 3:
        print(f"\n  ... and {len(rows) - 3} more row(s)")


if __name__ == "__main__":
    main()
