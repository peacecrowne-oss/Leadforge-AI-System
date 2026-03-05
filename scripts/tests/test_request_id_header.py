"""Integration test: X-Request-Id header.

Validates:
  1. GET /health returns 200 and includes an X-Request-Id response header.
  2. If the request sends X-Request-Id: test-<uuid>, the response echoes
     the exact same value back in X-Request-Id.

Usage:
    python test_request_id_header.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import urllib.error
import urllib.request
import uuid


# ── HTTP helper ───────────────────────────────────────────────────────────────

def get_with_headers(url, req_headers=None):
    """Make a GET request; return (status_code, response_headers_dict, body_dict)."""
    req = urllib.request.Request(url, headers=(req_headers or {}), method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read())


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="X-Request-Id header integration test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # 1. GET /health → 200 and X-Request-Id is present in the response
    status, resp_headers, body = get_with_headers(f"{base}/health")
    assert status == 200, f"[request-id-present] Expected 200, got {status}: {body}"
    # Header lookup is case-insensitive
    lowered = {k.lower(): v for k, v in resp_headers.items()}
    assert "x-request-id" in lowered, (
        f"[request-id-present] X-Request-Id missing from response headers: "
        f"{list(resp_headers.keys())}"
    )

    # 2. GET /health with custom X-Request-Id → response echoes the same value
    custom_id = f"test-{uuid.uuid4()}"
    status, resp_headers, body = get_with_headers(
        f"{base}/health",
        req_headers={"X-Request-Id": custom_id},
    )
    assert status == 200, f"[request-id-echo] Expected 200, got {status}: {body}"
    lowered = {k.lower(): v for k, v in resp_headers.items()}
    assert "x-request-id" in lowered, (
        f"[request-id-echo] X-Request-Id missing from response headers: "
        f"{list(resp_headers.keys())}"
    )
    returned_id = lowered["x-request-id"]
    assert returned_id == custom_id, (
        f"[request-id-echo] Expected echoed id={custom_id!r}, got {returned_id!r}"
    )

    print("PASS test_request_id_header.py")


if __name__ == "__main__":
    main()
