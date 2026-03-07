#!/usr/bin/env python3
"""Integration test: Deterministic lead scoring (T11).

Steps:
  A. Score presence and range
     1.  Register + login a user.
     2.  POST /leads/search with fixed params.
     3.  Poll until complete; collect results.
     4.  Assert every lead has a numeric score in [0.0, 1.0].
     5.  Assert results are ordered highest-to-lowest by score.
     6.  Assert every lead has a score_explanation dict with the
         expected factor keys.

  B. Determinism
     7.  Run the identical search again (same params, new job).
     8.  Poll until complete; collect results.
     9.  Assert each position has the same full_name, score, and
         score_explanation values as the first run.

Usage:
    python test_lead_scoring.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

EXPECTED_EXPLANATION_KEYS = {
    "seniority_match",
    "title_match",
    "keyword_match",
    "location_match",
    "company_match",
}


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
    assert status == 200, f"Login failed: {status} {text}"
    return json.loads(text)["access_token"]


def search_and_collect(base, auth, params, max_wait=30):
    """POST /leads/search, poll to completion, return results list."""
    status, body = request_json("POST", f"{base}/leads/search", params, headers=auth)
    assert status == 202, f"[search] Expected 202, got {status}: {body}"
    job_id = body["job_id"]

    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, job = request_json("GET", f"{base}/leads/jobs/{job_id}", headers=auth)
        assert status == 200, f"[poll] {status} {job}"
        if job["status"] == "complete":
            break
        if job["status"] == "failed":
            raise AssertionError(f"Job failed: {job}")
        time.sleep(1)
    else:
        raise AssertionError(f"Job {job_id} did not complete within {max_wait}s")

    status, res = request_json("GET", f"{base}/leads/jobs/{job_id}/results", headers=auth)
    assert status == 200, f"[results] {status} {res}"
    return job_id, res["results"]


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lead scoring determinism test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    email = f"scoring_{uuid.uuid4().hex[:8]}@example.com"
    token = register_and_login(base, email, "TestPass123")
    auth = {"Authorization": f"Bearer {token}"}

    search_params = {"keywords": "engineer", "location": "San Francisco, CA", "limit": 5}

    # ── A: Score presence, range, ordering, explanation ───────────────────────

    _, leads1 = search_and_collect(base, auth, search_params)

    assert len(leads1) > 0, "[A] No leads returned"

    for lead in leads1:
        score = lead.get("score")
        assert score is not None, f"[A] Lead {lead['id']} has no score"
        assert isinstance(score, (int, float)), f"[A] score is not numeric: {score}"
        assert 0.0 <= score <= 1.0, f"[A] score out of range: {score}"

        explanation = lead.get("score_explanation")
        assert explanation is not None, f"[A] Lead {lead['id']} has no score_explanation"
        assert isinstance(explanation, dict), f"[A] score_explanation is not a dict"
        missing = EXPECTED_EXPLANATION_KEYS - set(explanation.keys())
        assert not missing, f"[A] Missing explanation keys: {missing}"
        for key, val in explanation.items():
            assert isinstance(val, (int, float)), f"[A] explanation[{key}] not numeric"
            assert val >= 0.0, f"[A] explanation[{key}] negative: {val}"

    # Verify results are sorted descending by score
    scores1 = [lead["score"] for lead in leads1]
    assert scores1 == sorted(scores1, reverse=True), (
        f"[A] Results not sorted by score descending: {scores1}"
    )

    # ── B: Determinism — identical search must produce identical scores ────────

    _, leads2 = search_and_collect(base, auth, search_params)

    assert len(leads2) == len(leads1), (
        f"[B] Result count changed: {len(leads1)} vs {len(leads2)}"
    )

    for idx, (l1, l2) in enumerate(zip(leads1, leads2)):
        assert l1["full_name"] == l2["full_name"], (
            f"[B] Position {idx} name mismatch: {l1['full_name']!r} vs {l2['full_name']!r}"
        )
        assert l1["score"] == l2["score"], (
            f"[B] Position {idx} ({l1['full_name']}) score changed: "
            f"{l1['score']} vs {l2['score']}"
        )
        assert l1["score_explanation"] == l2["score_explanation"], (
            f"[B] Position {idx} ({l1['full_name']}) explanation changed"
        )

    n = len(leads1)
    lo = min(scores1)
    hi = max(scores1)
    print(
        f"PASS test_lead_scoring.py  "
        f"(N={n} leads, score range [{lo:.4f}–{hi:.4f}], determinism verified)"
    )


if __name__ == "__main__":
    main()
