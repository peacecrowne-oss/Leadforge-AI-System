#!/usr/bin/env python3
"""LeadForge backend summary verification.

Validates seven system-level claims:
  1. Backend is reachable (Docker container up)
  2. Health endpoint returns {"status": "ok"}
  3. Auth flow: register + login returns access_token
  4. Protected endpoints enforce JWT (401 without token)
  5. Lead search job runs end-to-end (queued → complete)
  6. Results are deterministic (two identical reads of the same job)
  7. CSV export returns a valid CSV file

Usage:
    python test_summary_verification.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.parse
import uuid


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _conn(host: str, port: int) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(host, port, timeout=10)


def request(
    host: str,
    port: int,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    form_body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict[str, str], str]:
    """Make one HTTP request; return (status, lowercased-headers-dict, body-text)."""
    req_headers: dict[str, str] = dict(headers or {})
    body: bytes | None = None

    if json_body is not None:
        body = json.dumps(json_body).encode()
        req_headers.setdefault("Content-Type", "application/json")

    if form_body is not None:
        body = urllib.parse.urlencode(form_body).encode()
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    if body is not None:
        req_headers["Content-Length"] = str(len(body))

    conn = _conn(host, port)
    try:
        conn.request(method, path, body=body, headers=req_headers)
        resp = conn.getresponse()
        status = resp.status
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        resp_body = resp.read().decode("utf-8")
    finally:
        conn.close()

    return status, resp_headers, resp_body


# ── Auth helper ───────────────────────────────────────────────────────────────

def get_token(host: str, port: int) -> str:
    """Register a unique user and return a valid JWT access token."""
    email = f"verify_{uuid.uuid4().hex[:8]}@example.com"
    password = "VerifyPass123!"

    request(host, port, "POST", "/auth/register", json_body={"email": email, "password": password})

    status, _, body = request(
        host, port, "POST", "/auth/login",
        form_body={"username": email, "password": password},
    )
    if status != 200:
        raise RuntimeError(f"Login failed ({status}): {body}")
    return json.loads(body)["access_token"]


# ── Individual tests ───────────────────────────────────────────────────────────

def test_reachable(host: str, port: int) -> bool:
    """1. Backend is reachable (Docker container up)."""
    try:
        status, _, _ = request(host, port, "GET", "/health")
        if status == 200:
            print("PASS 1 — backend reachable")
            return True
        print(f"FAIL 1 — backend reachable: /health returned {status}")
        return False
    except OSError as exc:
        print(f"FAIL 1 — backend reachable: cannot connect to {host}:{port} — {exc}")
        print("         Is the container running?  docker compose up -d")
        return False


def test_health(host: str, port: int) -> bool:
    """2. Health endpoint returns {\"status\": \"ok\"}."""
    status, _, body = request(host, port, "GET", "/health")
    if status != 200:
        print(f"FAIL 2 — health: expected 200, got {status}")
        return False
    data = json.loads(body)
    if data.get("status") != "ok":
        print(f"FAIL 2 — health: expected {{\"status\":\"ok\"}}, got {data}")
        return False
    print("PASS 2 — health endpoint")
    return True


def test_auth_flow(host: str, port: int) -> tuple[bool, str]:
    """3. Register + login returns access_token with token_type bearer.

    Returns (passed, token) so later tests can reuse the token.
    """
    email = f"flow_{uuid.uuid4().hex[:8]}@example.com"
    password = "FlowPass123!"

    # Register — 201 on new email, 409 on duplicate; both are acceptable.
    status, _, _ = request(host, port, "POST", "/auth/register",
                           json_body={"email": email, "password": password})
    if status not in (200, 201, 409):
        print(f"FAIL 3 — auth flow: register returned {status}")
        return False, ""

    # Login — must return 200 with access_token and token_type=bearer
    status, _, body = request(host, port, "POST", "/auth/login",
                               form_body={"username": email, "password": password})
    if status != 200:
        print(f"FAIL 3 — auth flow: login returned {status}: {body}")
        return False, ""

    data = json.loads(body)
    if "access_token" not in data:
        print(f"FAIL 3 — auth flow: missing access_token in {data}")
        return False, ""
    if data.get("token_type") != "bearer":
        print(f"FAIL 3 — auth flow: expected token_type=bearer, got {data.get('token_type')}")
        return False, ""

    print("PASS 3 — auth flow")
    return True, data["access_token"]


def test_jwt_enforced(host: str, port: int) -> bool:
    """4. POST /leads/search without a token must return 401."""
    status, _, body = request(host, port, "POST", "/leads/search",
                               json_body={"keywords": "engineer"})
    if status != 401:
        print(f"FAIL 4 — JWT enforced: expected 401, got {status}: {body}")
        return False
    print("PASS 4 — protected endpoint enforces JWT")
    return True


def test_job_end_to_end(host: str, port: int, token: str) -> tuple[bool, str]:
    """5. Create a search job and poll until complete (≤ 60 s).

    Returns (passed, job_id) so tests 6 and 7 can reuse the completed job.
    """
    auth = {"Authorization": f"Bearer {token}"}

    # Create job
    status, _, body = request(host, port, "POST", "/leads/search",
                               json_body={"keywords": "engineer"}, headers=auth)
    if status not in (200, 202):
        print(f"FAIL 5 — job end-to-end: create returned {status}: {body}")
        return False, ""

    job_id: str = json.loads(body).get("job_id", "")
    if not job_id:
        print(f"FAIL 5 — job end-to-end: no job_id in response: {body}")
        return False, ""

    # Poll until terminal status
    deadline = time.time() + 60
    while time.time() < deadline:
        status, _, body = request(host, port, "GET", f"/leads/jobs/{job_id}", headers=auth)
        if status != 200:
            print(f"FAIL 5 — job end-to-end: polling returned {status}: {body}")
            return False, ""
        data = json.loads(body)
        job_status = data.get("status")
        if job_status == "complete":
            print("PASS 5 — lead search job end-to-end")
            return True, job_id
        if job_status == "failed":
            print(f"FAIL 5 — job end-to-end: job failed: {data.get('error')}")
            return False, ""
        time.sleep(1)

    print("FAIL 5 — job end-to-end: job did not complete within 60 s")
    return False, ""


def test_results_deterministic(host: str, port: int, token: str, job_id: str) -> bool:
    """6. Two consecutive reads of the same job's results must be identical."""
    auth = {"Authorization": f"Bearer {token}"}
    path = f"/leads/jobs/{job_id}/results?offset=0&limit=200"

    status1, _, body1 = request(host, port, "GET", path, headers=auth)
    status2, _, body2 = request(host, port, "GET", path, headers=auth)

    if status1 != 200:
        print(f"FAIL 6 — deterministic results: first read returned {status1}")
        return False
    if status2 != 200:
        print(f"FAIL 6 — deterministic results: second read returned {status2}")
        return False

    data1 = json.loads(body1)
    data2 = json.loads(body2)

    # Compare count and every result's stable fields (id is fixed after job runs).
    if data1.get("count") != data2.get("count"):
        print(
            f"FAIL 6 — deterministic results: count changed "
            f"({data1.get('count')} → {data2.get('count')})"
        )
        return False

    results1 = data1.get("results", [])
    results2 = data2.get("results", [])

    if results1 != results2:
        print("FAIL 6 — deterministic results: result lists differ between reads")
        return False

    print(f"PASS 6 — results deterministic ({data1.get('count')} leads, two reads match)")
    return True


def test_csv_export(host: str, port: int, token: str, job_id: str) -> bool:
    """7. CSV export returns 200, Content-Type text/csv, with expected header row."""
    auth = {"Authorization": f"Bearer {token}"}
    status, resp_headers, body = request(
        host, port, "GET", f"/leads/jobs/{job_id}/export.csv", headers=auth
    )

    if status != 200:
        print(f"FAIL 7 — CSV export: expected 200, got {status}: {body}")
        return False

    content_type = resp_headers.get("content-type", "")
    if "text/csv" not in content_type:
        print(f"FAIL 7 — CSV export: expected text/csv Content-Type, got '{content_type}'")
        return False

    lines = body.strip().splitlines()
    if not lines:
        print("FAIL 7 — CSV export: empty response body")
        return False

    expected_header = "id,full_name,title,company,location,email,linkedin_url,score"
    if lines[0] != expected_header:
        print(f"FAIL 7 — CSV export: unexpected header row: {lines[0]!r}")
        return False

    print(f"PASS 7 — CSV export ({len(lines) - 1} data rows)")
    return True


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="LeadForge backend summary verification")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000",
                    help="Base URL of the running backend (default: http://127.0.0.1:8000)")
    args = ap.parse_args()

    parsed = urllib.parse.urlparse(args.base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    print(f"Target: {args.base_url}\n")

    failures = 0

    # 1 — reachable
    if not test_reachable(host, port):
        failures += 1
        # Cannot proceed if the server is down.
        print("\nFATAL: backend is unreachable; aborting remaining tests.")
        sys.exit(1)

    # 2 — health
    if not test_health(host, port):
        failures += 1

    # 3 — auth flow (token needed for later tests)
    auth_ok, token = test_auth_flow(host, port)
    if not auth_ok:
        failures += 1

    # 4 — JWT enforced (no token needed)
    if not test_jwt_enforced(host, port):
        failures += 1

    if not auth_ok:
        print("\nSkipping tests 5-7: no valid token (auth flow failed).")
        sys.exit(1)

    # 5 — end-to-end job (job_id needed for tests 6 and 7)
    job_ok, job_id = test_job_end_to_end(host, port, token)
    if not job_ok:
        failures += 1

    if not job_ok:
        print("\nSkipping tests 6-7: no completed job (end-to-end test failed).")
        sys.exit(1)

    # 6 — deterministic results
    if not test_results_deterministic(host, port, token, job_id):
        failures += 1

    # 7 — CSV export
    if not test_csv_export(host, port, token, job_id):
        failures += 1

    # ── Final verdict ─────────────────────────────────────────────────────────
    print()
    if failures == 0:
        print("ALL TESTS PASSED — LeadForge backend verified.")
    else:
        print(f"{failures} TEST(S) FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
