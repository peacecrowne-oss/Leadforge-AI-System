"""Integration test: Structured error envelope.

Validates that every error response uses the standard envelope:
    {"error": {"code": "...", "message": "...", ["details": ...]}}

Cases:
  1. POST /leads/search without token → 401 with code "UNAUTHORIZED"
  2. POST /leads/search with valid token + invalid body
     (limit="not-an-int") → 422 with code "VALIDATION_ERROR" and "details"

Usage:
    python test_error_envelope.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
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
    parser = argparse.ArgumentParser(description="Error envelope integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # 1. POST /leads/search without token → 401 UNAUTHORIZED error envelope
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer"},
    )
    assert status == 401, f"[401-envelope] Expected 401, got {status}: {body}"
    assert "error" in body, f"[401-envelope] Missing 'error' key: {body}"
    assert body["error"].get("code") == "UNAUTHORIZED", (
        f"[401-envelope] Expected code UNAUTHORIZED: {body}"
    )
    assert "message" in body["error"], f"[401-envelope] Missing 'message': {body}"

    # 2. Register + login to get a valid token for the body-validation test
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    request_json("POST", f"{base}/auth/register", {"email": email, "password": password})
    status, login_body = request_form(
        "POST", f"{base}/auth/login",
        {"username": email, "password": password},
    )
    assert status == 200, f"[422-setup] Login failed: {status}: {login_body}"
    token = login_body["access_token"]

    # 3. POST /leads/search with valid token + invalid body (limit as string) → 422
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"limit": "not-an-int"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status == 422, f"[422-envelope] Expected 422, got {status}: {body}"
    assert "error" in body, f"[422-envelope] Missing 'error' key: {body}"
    assert body["error"].get("code") == "VALIDATION_ERROR", (
        f"[422-envelope] Expected code VALIDATION_ERROR: {body}"
    )
    assert "details" in body["error"], (
        f"[422-envelope] Expected 'details' key in error for 422: {body}"
    )

    print("PASS test_error_envelope.py")


if __name__ == "__main__":
    main()
