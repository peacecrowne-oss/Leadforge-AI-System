#!/usr/bin/env python3
"""Integration test: Campaign execution engine.

Steps:
  A. Execution flow
     1.  Register + login user A.
     2.  POST /leads/search — trigger a search job.
     3.  Poll until complete; collect job_id + up to 5 lead IDs.
     4.  POST /campaigns — create a campaign.
     5.  Assign all collected leads to the campaign.
     6.  POST /campaigns/{id}/run — execute; expect 200 with stats.
     7.  Verify deterministic metrics match the formula:
           sent      = N
           opened    = (N * 3) // 5
           replied   = (opened * 3) // 10
           failed    = 0
     8.  GET /campaigns/{id}/stats — verify same values as the run response.
     9.  POST /campaigns/{id}/run again — expect identical stats (deterministic).

  B. Edge case
     10. POST /campaigns/{empty_id}/run (no leads) — expect 422.

  C. Cross-user isolation
     11. Register + login user B.
     12. POST /campaigns/{id}/run as user B — expect 404.
     13. GET /campaigns/{id}/stats as user B — expect 404.

  D. Regression: existing tests are run separately; this test only adds
     new execution assertions.

Usage:
    python test_campaign_execution.py --base-url http://127.0.0.1:8000
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
    data, req_headers = None, {}
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
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, body = request_json("GET", f"{base}/leads/jobs/{job_id}", headers=auth)
        assert status == 200, f"Poll failed: {status} {body}"
        if body["status"] in ("complete", "failed"):
            return body
        time.sleep(1)
    raise AssertionError(f"Job {job_id} did not complete within {max_wait}s")


def expected_stats(n):
    """Mirror the deterministic formula from _compute_stats."""
    sent = n
    opened = (sent * 3) // 5
    replied = (opened * 3) // 10
    return {
        "total_leads": n,
        "processed_leads": n,
        "sent_count": sent,
        "opened_count": opened,
        "replied_count": replied,
        "failed_count": 0,
    }


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Campaign execution test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    password = "TestPass123"
    email_a = f"exec_a_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"exec_b_{uuid.uuid4().hex[:8]}@example.com"

    # ── A: Execution flow ─────────────────────────────────────────────────────

    # 1. User A
    token_a = register_and_login(base, email_a, password)
    auth_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Search job
    status, body = request_json(
        "POST", f"{base}/leads/search",
        {"keywords": "engineer", "limit": 5},
        headers=auth_a,
    )
    assert status == 202, f"[search] Expected 202, got {status}: {body}"
    job_id = body["job_id"]

    # 3. Poll + collect leads
    job = wait_for_job(base, job_id, auth_a)
    assert job["status"] == "complete", f"[search] Job failed: {job}"
    status, results_body = request_json(
        "GET", f"{base}/leads/jobs/{job_id}/results", headers=auth_a
    )
    assert status == 200, f"[results] Expected 200, got {status}"
    leads = results_body["results"]
    assert len(leads) > 0, "[results] No leads returned"
    leads = leads[:5]  # use up to 5

    # 4. Create campaign
    status, campaign = request_json(
        "POST", f"{base}/campaigns",
        {"name": "Execution Test Campaign"},
        headers=auth_a,
    )
    assert status == 201, f"[campaign] Expected 201, got {status}: {campaign}"
    campaign_id = campaign["id"]

    # 5. Assign all leads
    for lead in leads:
        status, _ = request_json(
            "POST", f"{base}/campaigns/{campaign_id}/leads",
            {"job_id": job_id, "lead_id": lead["id"]},
            headers=auth_a,
        )
        assert status == 201, f"[assign] Expected 201 for lead {lead['id']}, got {status}"

    n = len(leads)
    exp = expected_stats(n)

    # 6. Run campaign
    status, run_body = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/run", headers=auth_a
    )
    assert status == 200, f"[run] Expected 200, got {status}: {run_body}"
    assert run_body["execution_status"] == "completed", f"[run] wrong status: {run_body}"

    # 7. Verify deterministic metrics
    for field, expected_val in exp.items():
        assert run_body[field] == expected_val, (
            f"[run] {field}: expected {expected_val}, got {run_body[field]}"
        )
    assert run_body["campaign_id"] == campaign_id
    assert run_body["last_run_at"] is not None

    # 8. GET /stats → same values
    status, stats_body = request_json(
        "GET", f"{base}/campaigns/{campaign_id}/stats", headers=auth_a
    )
    assert status == 200, f"[stats] Expected 200, got {status}: {stats_body}"
    for field, expected_val in exp.items():
        assert stats_body[field] == expected_val, (
            f"[stats] {field}: expected {expected_val}, got {stats_body[field]}"
        )

    # 9. Run again → identical metrics (deterministic)
    status, run2_body = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/run", headers=auth_a
    )
    assert status == 200, f"[run2] Expected 200, got {status}: {run2_body}"
    for field, expected_val in exp.items():
        assert run2_body[field] == expected_val, (
            f"[run2] {field}: expected {expected_val}, got {run2_body[field]}"
        )

    # ── B: Edge case — no leads ───────────────────────────────────────────────

    # 10. Empty campaign → 422
    status, empty_campaign = request_json(
        "POST", f"{base}/campaigns",
        {"name": "Empty Campaign"},
        headers=auth_a,
    )
    assert status == 201, f"[empty-campaign] Expected 201, got {status}"
    empty_id = empty_campaign["id"]

    status, err_body = request_json(
        "POST", f"{base}/campaigns/{empty_id}/run", headers=auth_a
    )
    assert status == 422, f"[no-leads] Expected 422, got {status}: {err_body}"

    # ── C: Cross-user isolation ───────────────────────────────────────────────

    # 11. User B
    token_b = register_and_login(base, email_b, password)
    auth_b = {"Authorization": f"Bearer {token_b}"}

    # 12. User B run user A's campaign → 404
    status, body = request_json(
        "POST", f"{base}/campaigns/{campaign_id}/run", headers=auth_b
    )
    assert status == 404, f"[isolation-run] Expected 404 for user B, got {status}: {body}"

    # 13. User B get stats → 404
    status, body = request_json(
        "GET", f"{base}/campaigns/{campaign_id}/stats", headers=auth_b
    )
    assert status == 404, f"[isolation-stats] Expected 404 for user B, got {status}: {body}"

    print(f"PASS test_campaign_execution.py  (N={n} leads, opened={exp['opened_count']}, replied={exp['replied_count']})")


if __name__ == "__main__":
    main()
