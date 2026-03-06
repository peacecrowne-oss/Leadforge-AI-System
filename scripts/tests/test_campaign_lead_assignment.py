#!/usr/bin/env python3
"""Integration test: Campaign lead assignment and cross-user isolation.

Steps:
  1.  Register + login user A.
  2.  POST /leads/search — trigger a search job.
  3.  Poll until the job is complete, collect job_id + first lead_id.
  4.  POST /campaigns — create a campaign as user A.
  5.  POST /campaigns/{id}/leads — assign the lead (expect 201).
  6.  GET  /campaigns/{id}/leads — verify lead appears in the list.
  7.  POST /campaigns/{id}/leads (same lead) — expect 409 duplicate.
  8.  Register + login user B.
  9.  POST /campaigns/{id}/leads as user B — expect 404.
  10. GET  /campaigns/{id}/leads as user B — expect 404.
  11. DELETE /campaigns/{id}/leads/{lead_id} as user B — expect 404.
  12. DELETE /campaigns/{id}/leads/{lead_id} as user A — expect 204.
  13. GET  /campaigns/{id}/leads as user A — expect empty list.

Usage:
    python test_campaign_lead_assignment.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method, url, body=None, headers=None, content_type="application/json"):
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
    _request("POST", f"{base}/auth/register", {"email": email, "password": password})
    status, text = _request(
        "POST", f"{base}/auth/login",
        {"username": email, "password": password},
        content_type="application/x-www-form-urlencoded",
    )
    assert status == 200, f"Login failed for {email}: {status} {text}"
    return json.loads(text)["access_token"]


def wait_for_job(base, job_id, auth, max_wait=30):
    """Poll /leads/jobs/{job_id} until status is complete or failed."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, body = request_json("GET", f"{base}/leads/jobs/{job_id}", headers=auth)
        assert status == 200, f"Poll failed: {status} {body}"
        if body["status"] in ("complete", "failed"):
            return body
        time.sleep(1)
    raise AssertionError(f"Job {job_id} did not complete within {max_wait}s")


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Campaign lead assignment test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    password = "TestPass123!"
    email_a = f"lead_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"lead_b_{uuid.uuid4().hex[:8]}@example.com"

    # 1. User A: register + login
    token_a = register_and_login(base, email_a, password)
    auth_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Create a search job
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer", "limit": 5},
        headers=auth_a,
    )
    assert status == 202, f"[search] Expected 202, got {status}: {body}"
    job_id = body["job_id"]

    # 3. Poll until complete, collect first lead_id
    job = wait_for_job(base, job_id, auth_a)
    assert job["status"] == "complete", f"[search] Job failed: {job}"

    status, results_body = request_json(
        "GET", f"{base}/leads/jobs/{job_id}/results",
        headers=auth_a,
    )
    assert status == 200, f"[results] Expected 200, got {status}: {results_body}"
    results = results_body["results"]
    assert len(results) > 0, "[results] No leads returned"
    lead_id = results[0]["id"]

    # 4. Create campaign
    status, campaign = request_json(
        "POST", f"{base}/campaigns",
        {"name": "Lead Assignment Test Campaign"},
        headers=auth_a,
    )
    assert status == 201, f"[campaign] Expected 201, got {status}: {campaign}"
    campaign_id = campaign["id"]

    # 5. Assign lead → 201
    status, assignment = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/leads",
        {"job_id": job_id, "lead_id": lead_id},
        headers=auth_a,
    )
    assert status == 201, f"[add-lead] Expected 201, got {status}: {assignment}"
    assert assignment["lead_id"] == lead_id, f"[add-lead] lead_id mismatch: {assignment}"
    assert assignment["job_id"] == job_id, f"[add-lead] job_id mismatch: {assignment}"
    assert assignment["campaign_id"] == campaign_id

    # 6. List leads → lead appears
    status, leads = request_json(
        "GET", f"{base}/campaigns/{campaign_id}/leads", headers=auth_a
    )
    assert status == 200, f"[list-leads] Expected 200, got {status}: {leads}"
    assert len(leads) == 1, f"[list-leads] Expected 1 lead, got {len(leads)}: {leads}"
    assert leads[0]["lead_id"] == lead_id
    assert "full_name" in leads[0], f"[list-leads] full_name missing: {leads[0]}"

    # 7. Duplicate add → 409
    status, body = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/leads",
        {"job_id": job_id, "lead_id": lead_id},
        headers=auth_a,
    )
    assert status == 409, f"[duplicate] Expected 409, got {status}: {body}"

    # 8. User B: register + login
    token_b = register_and_login(base, email_b, password)
    auth_b = {"Authorization": f"Bearer {token_b}"}

    # 9. User B POST leads → 404
    status, body = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/leads",
        {"job_id": job_id, "lead_id": lead_id},
        headers=auth_b,
    )
    assert status == 404, f"[isolation-add] Expected 404 for user B, got {status}: {body}"

    # 10. User B GET leads → 404
    status, body = request_json(
        "GET", f"{base}/campaigns/{campaign_id}/leads", headers=auth_b
    )
    assert status == 404, f"[isolation-list] Expected 404 for user B, got {status}: {body}"

    # 11. User B DELETE lead → 404
    status, body = request_json(
        "DELETE", f"{base}/campaigns/{campaign_id}/leads/{lead_id}", headers=auth_b
    )
    assert status == 404, f"[isolation-remove] Expected 404 for user B, got {status}: {body}"

    # 12. User A DELETE lead → 204
    status, _ = _request("DELETE", f"{base}/campaigns/{campaign_id}/leads/{lead_id}",
                         headers=auth_a)
    assert status == 204, f"[remove] Expected 204, got {status}"

    # 13. User A GET leads → empty
    status, leads = request_json(
        "GET", f"{base}/campaigns/{campaign_id}/leads", headers=auth_a
    )
    assert status == 200, f"[post-remove-list] Expected 200, got {status}: {leads}"
    assert len(leads) == 0, f"[post-remove-list] Expected 0 leads, got {len(leads)}"

    print("PASS test_campaign_lead_assignment.py")


if __name__ == "__main__":
    main()
