#!/usr/bin/env python3
"""Integration test: Natural-language lead search (T12).

Sections:
  A. Query parsing   — POST /leads/nl-search returns expected parsed fields
                       for a structured NL query.
  B. Job ID returned — endpoint responds 202 with a valid job_id.
  C. Search job runs — polling job_id yields a completed job with leads.
  D. Auth enforced   — unauthenticated request returns 401.

Usage:
    python scripts/tests/test_nl_search.py --base-url http://127.0.0.1:8000
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


def rj(method, url, body=None, headers=None):
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


def poll_job(base, auth, job_id, max_wait=30):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, job = rj("GET", f"{base}/leads/jobs/{job_id}", headers=auth)
        assert status == 200, f"[poll] {status} {job}"
        if job["status"] == "complete":
            return job
        if job["status"] == "failed":
            raise AssertionError(f"Job failed: {job}")
        time.sleep(1)
    raise AssertionError(f"Job {job_id} did not complete within {max_wait}s")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NL lead search integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    email = f"nlsearch_{uuid.uuid4().hex[:8]}@example.com"
    token = register_and_login(base, email, "TestPass123")
    auth  = {"Authorization": f"Bearer {token}"}

    query = "Find senior engineers in San Francisco at OpenAI"

    # ── A: Parsing correctness ────────────────────────────────────────────────
    status, body = rj("POST", f"{base}/leads/nl-search", {"query": query}, headers=auth)
    assert status == 202, f"[A] Expected 202, got {status}: {body}"
    assert "parsed" in body, f"[A] Response missing 'parsed' field: {body}"

    parsed = body["parsed"]

    # title contains seniority word
    assert parsed.get("title") is not None, f"[A] title should be parsed, got: {parsed}"
    assert "senior" in parsed["title"].lower(), (
        f"[A] Expected 'senior' in title, got: {parsed['title']!r}"
    )

    # location contains city name
    assert parsed.get("location") is not None, f"[A] location should be parsed, got: {parsed}"
    assert "san francisco" in parsed["location"].lower(), (
        f"[A] Expected 'San Francisco' in location, got: {parsed['location']!r}"
    )

    # company extracted
    assert parsed.get("company") is not None, f"[A] company should be parsed, got: {parsed}"
    assert "openai" in parsed["company"].lower(), (
        f"[A] Expected 'OpenAI' in company, got: {parsed['company']!r}"
    )

    # limit defaults to 10 for this query (no "top N" present)
    assert isinstance(parsed.get("limit"), int), (
        f"[A] limit should be int, got: {parsed.get('limit')}"
    )
    assert parsed["limit"] == 10, f"[A] Expected default limit 10, got: {parsed['limit']}"

    print(f"[A] Parsing: PASS  {parsed}")

    # ── B: job_id returned ────────────────────────────────────────────────────
    assert "job_id" in body, f"[B] Response missing 'job_id': {body}"
    job_id = body["job_id"]
    assert isinstance(job_id, str) and len(job_id) == 36, (
        f"[B] Invalid job_id format: {job_id!r}"
    )
    print(f"[B] Job ID returned: PASS  ({job_id})")

    # ── C: Search job completes with leads ────────────────────────────────────
    job = poll_job(base, auth, job_id)
    assert job["status"] == "complete", f"[C] Job not complete: {job}"
    assert job["results_count"] > 0,    f"[C] Expected leads, got 0: {job}"

    status, res = rj("GET", f"{base}/leads/jobs/{job_id}/results", headers=auth)
    assert status == 200, f"[C] results endpoint {status}: {res}"
    assert len(res["results"]) > 0, "[C] No results in response"

    print(f"[C] Search job complete: PASS  ({job['results_count']} leads)")

    # ── D: Auth enforced ──────────────────────────────────────────────────────
    status, _ = rj("POST", f"{base}/leads/nl-search", {"query": query})
    assert status == 401, f"[D] Expected 401 without auth, got {status}"
    print("[D] Auth enforced: PASS")

    # ── "top N" limit parsing ─────────────────────────────────────────────────
    status, body2 = rj(
        "POST", f"{base}/leads/nl-search",
        {"query": "top 3 product managers at Stripe"},
        headers=auth,
    )
    assert status == 202, f"[limit] Expected 202, got {status}"
    assert body2["parsed"]["limit"] == 3, (
        f"[limit] Expected limit=3, got {body2['parsed']['limit']}"
    )
    print(f"[limit] 'top N' parsed: PASS  (limit={body2['parsed']['limit']})")

    print(
        f"\nPASS test_nl_search.py  "
        f"(query parsed, job_id returned, {job['results_count']} leads, auth enforced)"
    )


if __name__ == "__main__":
    main()
