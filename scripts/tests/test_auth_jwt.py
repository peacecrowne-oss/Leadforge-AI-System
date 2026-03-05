"""Integration test: JWT Authentication.

Validates:
  - GET /health returns 200 JSON
  - POST /auth/register accepts 201/409
  - POST /auth/login (form-encoded username/password) returns access_token + bearer
  - POST /leads/search without token returns 401
  - POST /leads/search with token returns 200/202 with job_id

Usage:
    python test_auth_jwt.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import sys
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


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auth JWT integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # 1. GET /health → 200 JSON
    status, body = request_json("GET", f"{base}/health")
    assert status == 200, f"[health] Expected 200, got {status}: {body}"
    assert "status" in body, f"[health] Expected 'status' key: {body}"

    # 2. POST /auth/register → 201 on new email, 409 on duplicate (both ok)
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    status, body = request_json(
        "POST", f"{base}/auth/register",
        {"email": email, "password": password},
    )
    assert status in (200, 201, 409), (
        f"[register] Expected 201/409, got {status}: {body}"
    )

    # 3. POST /auth/login → form fields username/password → access_token + bearer
    status, body = request_form(
        "POST", f"{base}/auth/login",
        {"username": email, "password": password},
    )
    assert status == 200, f"[login] Expected 200, got {status}: {body}"
    assert "access_token" in body, f"[login] Missing access_token: {body}"
    assert body.get("token_type") == "bearer", f"[login] Expected token_type='bearer': {body}"
    token = body["access_token"]

    # 4. POST /leads/search without token → 401
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer"},
    )
    assert status == 401, f"[search-no-auth] Expected 401, got {status}: {body}"

    # 5. POST /leads/search with valid token → 200/202 with job_id
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status in (200, 202), f"[search-auth] Expected 200/202, got {status}: {body}"
    assert "job_id" in body, f"[search-auth] Missing job_id: {body}"

    print("PASS test_auth_jwt.py")


if __name__ == "__main__":
    main()
