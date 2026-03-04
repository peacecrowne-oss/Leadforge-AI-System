#!/usr/bin/env python3
"""Smoke test for LeadForge AI backend — T12-PY Contract Regression.

Validates the end-to-end authenticated lead-search contract:
  1. GET /health          — server reachable, returns JSON
  2. POST /auth/register  — create (or accept existing) test user
  3. POST /auth/login     — form-login returns bearer token
  4a. POST /leads/search  WITHOUT auth — must return 401
  4b. POST /leads/search  WITH auth    — must return 202 + job_id
  5a. Poll /leads/jobs/{job_id}        — wait for "complete" (max 30 s)
  5b. GET  /leads/jobs/{job_id}/results — schema: count (int), results (list)
  5c. Same call twice                  — first-page lead IDs must be identical
  6.  GET  /leads/jobs/{job_id}/export.csv — 200, text/csv, valid header row

Usage:
    python scripts/smoke_test.py [--base-url http://127.0.0.1:8000]

Exit code: 0 on all steps passing, 1 on first failure.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LeadForge contract regression smoke test")
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        metavar="URL",
        help="Base URL of the running backend (default: http://127.0.0.1:8000)",
    )
    return p.parse_args()


# ── Step counter & assertion helpers ─────────────────────────────────────────

_STEP_NUM = 0


def step(label: str) -> None:
    global _STEP_NUM
    _STEP_NUM += 1
    print(f"\n[{_STEP_NUM}] {label}")


def assert_true(condition: bool, message: str) -> None:
    """Print PASS/FAIL and exit 1 on failure."""
    if condition:
        print(f"    PASS  {message}")
    else:
        print(f"    FAIL  {message}")
        sys.exit(1)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def request_json(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    """HTTP request with optional JSON body; returns (status_code, parsed_json).

    Never raises on HTTP error codes — the caller inspects the status.
    """
    data: bytes | None = None
    req_headers: dict = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            payload = {}
        return exc.code, payload


def request_form(
    url: str,
    fields: dict,
    headers: dict | None = None,
) -> tuple[int, dict]:
    """POST application/x-www-form-urlencoded; returns (status_code, parsed_json)."""
    data = urllib.parse.urlencode(fields).encode()
    req_headers: dict = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            payload = {}
        return exc.code, payload


def request_text(
    method: str,
    url: str,
    headers: dict | None = None,
) -> tuple[int, str, object]:
    """HTTP request; returns (status_code, body_text, http_headers).

    ``http_headers`` is the raw http.client.HTTPMessage (supports
    case-insensitive ``.get()`` lookups).  On error it is ``e.headers``.
    """
    req_headers: dict = {}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode(errors="replace"), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace"), exc.headers


# ── Main test runner ──────────────────────────────────────────────────────────

def run(base: str) -> None:
    base = base.rstrip("/")

    # Unique test user per run so parallel runs never collide.
    run_id = uuid.uuid4().hex[:8]
    email = f"smoke_{run_id}@leadforge.test"
    password = "Smoke$Test99!"

    # ------------------------------------------------------------------ 1 ---
    step("GET /health — server reachable and returns JSON")
    status, body = request_json("GET", f"{base}/health")
    assert_true(
        status == 200,
        f"status 200  (got {status}, body={body!r})",
    )
    assert_true(isinstance(body, dict), f"body is a JSON object  (got {body!r})")

    # ------------------------------------------------------------------ 2 ---
    step(f"POST /auth/register — register {email}")
    status, body = request_json(
        "POST",
        f"{base}/auth/register",
        body={"email": email, "password": password},
    )
    assert_true(
        status in (200, 201, 409),
        f"status 201 or 409  (got {status}, body={body!r})",
    )
    if status == 409:
        print("    NOTE  user already existed — continuing")

    # ------------------------------------------------------------------ 3 ---
    # OAuth2PasswordRequestForm requires the field name 'username' (not 'email').
    step("POST /auth/login — form login, expect bearer token")
    status, body = request_form(
        f"{base}/auth/login",
        {"username": email, "password": password},
    )
    assert_true(status == 200, f"status 200  (got {status}, body={body!r})")
    token: str = body.get("access_token", "")
    assert_true(bool(token), f"access_token present in response  (got {body!r})")
    token_type: str = body.get("token_type", "")
    assert_true(
        token_type.lower() == "bearer",
        f"token_type is 'bearer'  (got {token_type!r})",
    )
    auth_header = {"Authorization": f"Bearer {token}"}

    # ---------------------------------------------------------------- 4a ---
    step("POST /leads/search WITHOUT Authorization — must return 401")
    status, body = request_json(
        "POST",
        f"{base}/leads/search",
        body={"keywords": "smoke test", "limit": 5},
        # intentionally no auth_header
    )
    assert_true(status == 401, f"status 401  (got {status}, body={body!r})")

    # ---------------------------------------------------------------- 4b ---
    step("POST /leads/search WITH Authorization — must return 202 + job_id")
    status, body = request_json(
        "POST",
        f"{base}/leads/search",
        body={"keywords": "smoke test", "limit": 5},
        headers=auth_header,
    )
    assert_true(status == 202, f"status 202  (got {status}, body={body!r})")
    job_id: str = body.get("job_id", "")
    assert_true(bool(job_id), f"job_id present in response  (got {body!r})")

    # ---------------------------------------------------------------- 5a ---
    step(f"GET /leads/jobs/{job_id} — poll until 'complete' (max 30 s)")
    deadline = time.monotonic() + 30
    job_state: str = "queued"
    last_body: dict = {}
    while time.monotonic() < deadline:
        status, last_body = request_json(
            "GET", f"{base}/leads/jobs/{job_id}", headers=auth_header
        )
        assert_true(
            status == 200,
            f"status 200 while polling  (got {status}, body={last_body!r})",
        )
        job_state = last_body.get("status", "")
        print(f"    ...   job status: {job_state}")
        if job_state in ("complete", "failed"):
            break
        time.sleep(1)
    assert_true(
        job_state in ("complete", "failed"),
        f"job reached a terminal state within 30 s  (last: {job_state!r})",
    )
    assert_true(
        job_state == "complete",
        f"job status is 'complete'  "
        f"(got '{job_state}', error={last_body.get('error')!r})",
    )

    # ---------------------------------------------------------------- 5b ---
    step(f"GET /leads/jobs/{job_id}/results — verify response schema")
    status, results_body = request_json(
        "GET",
        f"{base}/leads/jobs/{job_id}/results?offset=0&limit=10",
        headers=auth_header,
    )
    assert_true(status == 200, f"status 200  (got {status}, body={results_body!r})")
    assert_true(
        "count" in results_body,
        f"'count' key present  (got keys: {list(results_body.keys())})",
    )
    assert_true(
        isinstance(results_body["count"], int),
        f"count is int  (got {results_body['count']!r})",
    )
    assert_true(
        "results" in results_body,
        f"'results' key present  (got keys: {list(results_body.keys())})",
    )
    assert_true(
        isinstance(results_body["results"], list),
        f"results is a list  (got {type(results_body['results']).__name__})",
    )
    print(f"    NOTE  results_count={results_body['count']}, "
          f"page_size={len(results_body['results'])}")

    # ---------------------------------------------------------------- 5c ---
    step(f"GET /leads/jobs/{job_id}/results × 2 — ordering must be deterministic")
    _, results_body2 = request_json(
        "GET",
        f"{base}/leads/jobs/{job_id}/results?offset=0&limit=10",
        headers=auth_header,
    )
    ids_1 = [r.get("id") for r in results_body.get("results", [])]
    ids_2 = [r.get("id") for r in results_body2.get("results", [])]
    assert_true(
        ids_1 == ids_2,
        f"first-page lead IDs identical across two sequential calls\n"
        f"      call 1: {ids_1}\n"
        f"      call 2: {ids_2}",
    )

    # ------------------------------------------------------------------ 6 ---
    step(f"GET /leads/jobs/{job_id}/export.csv — valid CSV response")
    status, csv_text, resp_headers = request_text(
        "GET",
        f"{base}/leads/jobs/{job_id}/export.csv",
        headers=auth_header,
    )
    assert_true(status == 200, f"status 200  (got {status}, snippet={csv_text[:200]!r})")

    # resp_headers is http.client.HTTPMessage — case-insensitive .get()
    content_type: str = resp_headers.get("content-type") or ""
    assert_true(
        "text/csv" in content_type.lower(),
        f"Content-Type includes 'text/csv'  (got {content_type!r})",
    )

    csv_rows = list(csv.reader(io.StringIO(csv_text)))
    # Filter blank trailing rows that csv.writer sometimes emits.
    csv_rows = [r for r in csv_rows if any(cell.strip() for cell in r)]
    assert_true(
        len(csv_rows) >= 1,
        f"CSV has at least a header row  (got {len(csv_rows)} non-empty rows)",
    )
    header_row = csv_rows[0]
    required_csv_fields = {"id", "full_name", "score"}
    assert_true(
        required_csv_fields.issubset(set(header_row)),
        f"CSV header contains required fields {required_csv_fields}  "
        f"(got {header_row})",
    )
    data_rows = csv_rows[1:]
    print(f"    NOTE  CSV data rows: {len(data_rows)} "
          f"(0 is valid if no leads matched)")

    # ------------------------------------------------------------------ 7 ---
    step("Cross-user isolation — second user must get 404 on first user's job")
    run_id2 = uuid.uuid4().hex[:8]
    email2 = f"smoke2_{run_id2}@leadforge.test"
    status, _ = request_json(
        "POST", f"{base}/auth/register",
        body={"email": email2, "password": password},
    )
    assert_true(status in (200, 201, 409), f"register user2 status 201/409  (got {status})")
    status, body = request_form(
        f"{base}/auth/login", {"username": email2, "password": password}
    )
    assert_true(status == 200, f"login user2 status 200  (got {status})")
    token2 = body.get("access_token", "")
    assert_true(bool(token2), f"user2 access_token present  (got {body!r})")
    auth2 = {"Authorization": f"Bearer {token2}"}

    status, _ = request_json("GET", f"{base}/leads/jobs/{job_id}", headers=auth2)
    assert_true(status == 404, f"GET job status → 404 for non-owner  (got {status})")

    status, _ = request_json(
        "GET", f"{base}/leads/jobs/{job_id}/results?offset=0&limit=10", headers=auth2
    )
    assert_true(status == 404, f"GET job results → 404 for non-owner  (got {status})")

    status, _, _ = request_text(
        "GET", f"{base}/leads/jobs/{job_id}/export.csv", headers=auth2
    )
    assert_true(status == 404, f"GET export.csv → 404 for non-owner  (got {status})")

    # ---------------------------------------------------------------- done ---
    print(f"\n{'─' * 52}")
    print("  ALL STEPS PASSED")
    print(f"{'─' * 52}\n")


if __name__ == "__main__":
    args = parse_args()
    run(args.base_url)
