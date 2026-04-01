#!/usr/bin/env python3
"""Auto-import watcher for LeadForge CSV ingestion.

Polls a CSV file every 60 seconds. When the file's last-modified time has
changed since the previous run, it POSTs the file to:
    POST http://127.0.0.1:8000/leads/import/csv

Requirements:
    pip install requests

Usage:
    python scripts/auto_import_csv.py

Configuration:
    Set TOKEN below to a valid LeadForge JWT bearer token before running.
    Obtain one via: POST /auth/login -> access_token
"""
from __future__ import annotations

import os
import time

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

CSV_PATH   = "C:/AI PROJECTS1/INTERNSHIP/LeadForge-AI-System/apollo-leads.csv"
API_URL    = "http://127.0.0.1:8000/leads/import/csv"
TOKEN      = "<PASTE YOUR JWT TOKEN HERE>"
POLL_SECS  = 60

# ── State ─────────────────────────────────────────────────────────────────────

# Holds the mtime of the CSV as of the last successful import.
# None means the file has never been imported this session.
_last_mtime: float | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_mtime(path: str) -> float | None:
    """Return the file's last-modified timestamp, or None if it doesn't exist."""
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return None


def _import_csv(path: str) -> None:
    """POST the CSV file to the import endpoint and print the result."""
    with open(path, "rb") as f:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            files={"file": (os.path.basename(path), f, "text/csv")},
            timeout=30,
        )

    if response.status_code == 201:
        data = response.json()
        print(f"  job_id   : {data.get('job_id')}")
        print(f"  imported : {data.get('imported')} leads")
    else:
        print(f"  ERROR {response.status_code}: {response.text[:200]}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _last_mtime

    if TOKEN == "<PASTE YOUR JWT TOKEN HERE>":
        print("ERROR: Set TOKEN in this script before running.")
        print("       Obtain a token via: POST /auth/login -> access_token")
        return

    print(f"Watching: {CSV_PATH}")
    print(f"Polling every {POLL_SECS}s. Press Ctrl+C to stop.\n")

    while True:
        current_mtime = _get_mtime(CSV_PATH)

        if current_mtime is None:
            print(f"[{_now()}] File not found: {CSV_PATH}")

        elif current_mtime != _last_mtime:
            print(f"[{_now()}] Change detected — importing…")
            try:
                _import_csv(CSV_PATH)
                _last_mtime = current_mtime
            except requests.RequestException as exc:
                print(f"  Request failed: {exc}")

        else:
            print(f"[{_now()}] No change.")

        time.sleep(POLL_SECS)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
