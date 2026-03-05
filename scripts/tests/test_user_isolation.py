"""Integration test: Per-user job isolation.

Validates that user B cannot access jobs created by user A.

Steps:
  1. Register + login user A; create a /leads/search job.
  2. Poll /leads/jobs/{job_id} as user A until complete.
  3. Register + login user B.
  4. Access the following as user B — all must return 404:
       GET /leads/jobs/{job_id}
       GET /leads/jobs/{job_id}/results?offset=0&limit=10
       GET /leads/jobs/{job_id}/export.csv

Usage:
    python test_user_isolation.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def request_json(method, url, body=None, headers=None):
    """Make an HTTP request with a JSON body; return (status_code, dict)."""
    data = json.dumps(body).encode() if body is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def request_form(method, url, form_data, headers=None):
    """Make an HTTP request with a form-encoded body; return (status_code, dict)."""
    data = urllib.parse.urlencode(form_data).encode()
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def raw_get_status(url, headers=None):
    """Make a GET request; return the HTTP status code only (handles non-JSON too)."""
    req_headers = headers or {}
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


# ── Helpers ───────────────────────────────────────────────────────────────────

def register_and_login(base, email, password):
    """Register a user (ignore 409) and return a JWT access token."""
    request_json("POST", f"{base}/auth/register", {"email": email, "password": password})
    status, body = request_form(
        "POST", f"{base}/auth/login",
        {"username": email, "password": password},
    )
    assert status == 200, f"Login failed for {email}: {status} {body}"
    return body["access_token"]


def poll_job(base, job_id, token, timeout=30):
    """Poll until the job reaches a terminal status; return the final body."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, body = request_json(
            "GET", f"{base}/leads/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status == 200, f"Unexpected status while polling job: {status} {body}"
        if body.get("status") in ("complete", "failed"):
            return body
        time.sleep(1)
    raise AssertionError(f"Job {job_id} did not reach a terminal state within {timeout}s")


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="User isolation integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    password = "TestPass123!"
    email_a = f"user_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"user_b_{uuid.uuid4().hex[:8]}@example.com"

    # 1. User A: register, login, create search job
    token_a = register_and_login(base, email_a, password)
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert status in (200, 202), f"[user-A create job] Expected 202, got {status}: {body}"
    job_id = body["job_id"]

    # 2. Poll until complete (user A)
    poll_job(base, job_id, token_a)

    # 3. User B: register, login
    token_b = register_and_login(base, email_b, password)

    # 4a. User B: GET /leads/jobs/{job_id} → 404
    status, body = request_json(
        "GET", f"{base}/leads/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert status == 404, f"[isolation job] Expected 404 for user B, got {status}: {body}"

    # 4b. User B: GET /leads/jobs/{job_id}/results → 404
    status, body = request_json(
        "GET", f"{base}/leads/jobs/{job_id}/results?offset=0&limit=10",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert status == 404, f"[isolation results] Expected 404 for user B, got {status}: {body}"

    # 4c. User B: GET /leads/jobs/{job_id}/export.csv → 404
    #     The CSV endpoint may return non-JSON on success, so use raw_get_status.
    got = raw_get_status(
        f"{base}/leads/jobs/{job_id}/export.csv",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert got == 404, f"[isolation export.csv] Expected 404 for user B, got {got}"

    print("PASS test_user_isolation.py")


if __name__ == "__main__":
    main()
