#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def http(method, url, *, json_body=None, form_body=None, headers=None):
    headers = headers or {}
    data = None

    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    if form_body is not None:
        data = urlencode(form_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req) as r:
            body = r.read().decode()
            return r.status, body
    except HTTPError as e:
        body = e.read().decode()
        return e.code, body


def assert_error_envelope(body_text):
    j = json.loads(body_text)

    assert "error" in j
    assert "code" in j["error"]
    assert "message" in j["error"]

    return j


def get_token(base):
    """Register a unique user and return a valid Bearer token."""
    email = f"err_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"

    # Register — 201 on new email, 409 if already exists; both are fine.
    http(
        "POST",
        urljoin(base, "auth/register"),
        json_body={"email": email, "password": password},
    )

    # Login via OAuth2 form (username field holds the email).
    status, body = http(
        "POST",
        urljoin(base, "auth/login"),
        form_body={"username": email, "password": password},
    )
    assert status == 200, f"Login failed ({status}): {body}"
    return json.loads(body)["access_token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    base = args.base_url.rstrip("/") + "/"

    # 401 test
    status, body = http(
        "POST",
        urljoin(base, "leads/search"),
        json_body={"keywords": "test"}
    )

    assert status == 401
    assert_error_envelope(body)
    print("PASS 401 standardized error")

    # 422 test — requires a valid token so FastAPI reaches body validation
    token = get_token(base)
    status, body = http(
        "POST",
        urljoin(base, "leads/search"),
        json_body={"keywords": "x", "limit": "not-an-int"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status == 422, f"Expected 422, got {status}: {body}"
    assert_error_envelope(body)
    print("PASS 422 standardized error")

    # 404 test — use a known route that raises HTTPException(404) inside the app
    # so the response goes through the registered error envelope handler.
    fake_job_id = str(uuid.uuid4())
    status, body = http(
        "GET",
        urljoin(base, f"leads/jobs/{fake_job_id}"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status == 404, f"Expected 404, got {status}: {body}"
    assert_error_envelope(body)
    print("PASS 404 standardized error")

    print("PASS test_standardized_errors")


if __name__ == "__main__":
    main()
