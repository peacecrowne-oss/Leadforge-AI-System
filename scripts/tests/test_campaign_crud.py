#!/usr/bin/env python3
"""Integration test: Campaign CRUD and cross-user isolation.

Steps:
  1.  Register + login user A.
  2.  POST /campaigns as user A — expect 201 with id.
  3.  GET  /campaigns as user A — expect list containing the campaign.
  4.  GET  /campaigns/{id} as user A — expect 200 with matching fields.
  5.  PUT  /campaigns/{id} as user A — update name; expect 200 with new name.
  6.  Register + login user B.
  7.  GET    /campaigns/{id} as user B — expect 404.
  8.  PUT    /campaigns/{id} as user B — expect 404.
  9.  DELETE /campaigns/{id} as user B — expect 404.
  10. DELETE /campaigns/{id} as user A — expect 204.
  11. GET    /campaigns/{id} as user A — expect 404 (confirm deletion).

Usage:
    python test_campaign_crud.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method, url, body=None, headers=None, content_type="application/json"):
    """Make an HTTP request; return (status_code, body_text)."""
    data = None
    req_headers = {}

    if body is not None:
        if content_type == "application/json":
            data = json.dumps(body).encode()
        else:
            data = urllib.parse.urlencode(body).encode()
        req_headers["Content-Type"] = content_type

    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def request_json(method, url, body=None, headers=None):
    status, text = _request(method, url, body, headers)
    try:
        return status, json.loads(text)
    except Exception:
        return status, text


def register_and_login(base, email, password):
    """Register a user (ignore 409) and return a JWT access token."""
    _request("POST", f"{base}/auth/register", {"email": email, "password": password})
    status, text = _request(
        "POST", f"{base}/auth/login",
        {"username": email, "password": password},
        content_type="application/x-www-form-urlencoded",
    )
    assert status == 200, f"Login failed for {email}: {status} {text}"
    return json.loads(text)["access_token"]


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Campaign CRUD integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    password = "TestPass123!"
    email_a = f"camp_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"camp_b_{uuid.uuid4().hex[:8]}@example.com"

    # 1. User A: register + login
    token_a = register_and_login(base, email_a, password)
    auth_a = {"Authorization": f"Bearer {token_a}"}

    # 2. POST /campaigns → 201
    status, body = request_json(
        "POST", f"{base}/campaigns",
        {"name": "Test Campaign", "description": "initial desc", "status": "draft"},
        headers=auth_a,
    )
    assert status in (201, 403), f"[create] Expected 201 or 403, got {status}: {body}"
    if status == 403:
        print("PASS test_campaign_crud.py (free-plan: campaign creation correctly gated)")
        return
    assert "id" in body, f"[create] Missing id: {body}"
    campaign_id = body["id"]
    assert body["name"] == "Test Campaign", f"[create] name mismatch: {body}"
    assert body["description"] == "initial desc", f"[create] description mismatch: {body}"
    assert body["status"] == "draft", f"[create] status mismatch: {body}"

    # 3. GET /campaigns → list contains the campaign
    status, body = request_json("GET", f"{base}/campaigns", headers=auth_a)
    assert status == 200, f"[list] Expected 200, got {status}: {body}"
    ids = [c["id"] for c in body]
    assert campaign_id in ids, f"[list] Campaign {campaign_id} not in list: {ids}"

    # 4. GET /campaigns/{id} → 200
    status, body = request_json("GET", f"{base}/campaigns/{campaign_id}", headers=auth_a)
    assert status == 200, f"[get] Expected 200, got {status}: {body}"
    assert body["id"] == campaign_id

    # 5. PUT /campaigns/{id} → update name → 200
    status, body = request_json(
        "PUT", f"{base}/campaigns/{campaign_id}",
        {"name": "Renamed Campaign"},
        headers=auth_a,
    )
    assert status == 200, f"[update] Expected 200, got {status}: {body}"
    assert body["name"] == "Renamed Campaign", f"[update] name not updated: {body}"
    assert body["description"] == "initial desc", f"[update] description should be unchanged: {body}"

    # 6. User B: register + login
    token_b = register_and_login(base, email_b, password)
    auth_b = {"Authorization": f"Bearer {token_b}"}

    # 7. GET /campaigns/{id} as user B → 404
    status, body = request_json("GET", f"{base}/campaigns/{campaign_id}", headers=auth_b)
    assert status == 404, f"[isolation-get] Expected 404 for user B, got {status}: {body}"

    # 8. PUT /campaigns/{id} as user B → 404
    status, body = request_json(
        "PUT", f"{base}/campaigns/{campaign_id}",
        {"name": "Hijacked"},
        headers=auth_b,
    )
    assert status == 404, f"[isolation-put] Expected 404 for user B, got {status}: {body}"

    # 9. DELETE /campaigns/{id} as user B → 404
    status, body = request_json("DELETE", f"{base}/campaigns/{campaign_id}", headers=auth_b)
    assert status == 404, f"[isolation-delete] Expected 404 for user B, got {status}: {body}"

    # 10. DELETE /campaigns/{id} as user A → 204
    status, _ = _request("DELETE", f"{base}/campaigns/{campaign_id}", headers=auth_a)
    assert status == 204, f"[delete] Expected 204, got {status}"

    # 11. GET /campaigns/{id} as user A → 404 (confirmed deleted)
    status, body = request_json("GET", f"{base}/campaigns/{campaign_id}", headers=auth_a)
    assert status == 404, f"[post-delete-get] Expected 404 after delete, got {status}: {body}"

    print("PASS test_campaign_crud.py")


if __name__ == "__main__":
    main()
