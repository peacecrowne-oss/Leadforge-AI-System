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

import logging
import os
import time

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

CSV_PATH   = os.path.abspath("C:/AI PROJECTS1/INTERNSHIP/LeadForge-AI-System/apollo-leads.csv")
API_URL    = "http://127.0.0.1:8000/leads/import/csv"
LOGIN_URL  = "http://127.0.0.1:8000/auth/login"
USERNAME   = "test@leadforge.com"
PASSWORD   = "LeadForge!123"
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


MAX_RETRIES  = 3
RETRY_DELAY  = 2  # seconds between retries


def _get_token() -> str:
    """Log in and return a fresh JWT access token."""
    logger.info("USERNAME=%r PASSWORD=%r", USERNAME, PASSWORD)
    response = requests.post(
        "http://localhost:8000/auth/login",
        data={
            "username": USERNAME.strip(),
            "password": PASSWORD.strip()
        }
    )
    logger.info("Login status: %s", response.status_code)
    logger.info("Login response: %s", response.text)
    response.raise_for_status()
    return response.json()["access_token"]


def _import_csv(path: str) -> None:
    """POST the CSV file to the import endpoint and log the result."""
    logger.info("Import starting: %s", path)
    token = _get_token()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(path, "rb") as f:
                response = requests.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (os.path.basename(path), f, "text/csv")},
                    timeout=30,
                )

            if response.status_code == 201:
                data = response.json()
                logger.info("Import succeeded — job_id: %s  imported: %s leads",
                            data.get("job_id"), data.get("imported"))
                return

            # Non-201 response — log and retry
            logger.warning("Retry %s/%s — HTTP %s: %s",
                           attempt, MAX_RETRIES,
                           response.status_code, response.text[:200])

        except Exception as exc:
            logger.warning("Retry %s/%s — error: %s", attempt, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    logger.error("All %s retries failed for %s", MAX_RETRIES, path)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _last_mtime

    logger.info("Script started")
    logger.info("Watching : %s", CSV_PATH)
    logger.info("Poll interval: %ss — Press Ctrl+C to stop", POLL_SECS)

    startup_mtime = _get_mtime(CSV_PATH)
    logger.info("File mtime at startup: %s", startup_mtime)

    while True:
        current_mtime = _get_mtime(CSV_PATH)
        logger.info("--- poll ---  current mtime: %s  last mtime: %s",
                    current_mtime, _last_mtime)

        if current_mtime is None:
            logger.warning("File not found: %s", CSV_PATH)

        elif current_mtime != _last_mtime:
            logger.info("File change detected — starting import")
            try:
                _import_csv(CSV_PATH)
                _last_mtime = current_mtime
            except requests.RequestException as exc:
                logger.error("Request failed: %s", exc)

        else:
            logger.info("No change detected")

        time.sleep(POLL_SECS)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
