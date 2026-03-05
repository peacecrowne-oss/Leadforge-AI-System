#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def http(method, url, *, json_body=None, form_body=None, headers=None, timeout=20):
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
        with urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, body, dict(r.headers)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, dict(e.headers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/") + "/"

    run = uuid.uuid4().hex[:8]
    email = f"jwtcfg_{run}@leadforge.test"
    password = "JwtCfgPass!123"

    # health
    s, body, _ = http("GET", urljoin(base, "health"))
    assert s == 200, f"health failed: {s} {body}"

    # register
    s, body, _ = http("POST", urljoin(base, "auth/register"), json_body={"email": email, "password": password})
    assert s in (200, 201, 409), f"register failed: {s} {body}"

    # login must be 200 (this is the key check for your fix)
    s, body, _ = http("POST", urljoin(base, "auth/login"), form_body={"username": email, "password": password})
    assert s == 200, f"login failed: {s} {body}"

    j = json.loads(body)
    assert "access_token" in j, f"missing access_token: {j}"
    assert j.get("token_type", "").lower() == "bearer", f"token_type not bearer: {j}"

    token = j["access_token"]

    # protected endpoint should reject no token
    s, body, _ = http("POST", urljoin(base, "leads/search"), json_body={"keywords": "jwt config test", "limit": 1})
    assert s == 401, f"expected 401 without token: got {s} {body}"

    # protected endpoint should accept valid token
    s, body, _ = http(
        "POST",
        urljoin(base, "leads/search"),
        json_body={"keywords": "jwt config test", "limit": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert s in (200, 202), f"expected 200/202 with token: got {s} {body}"

    print("PASS test_jwt_config_ok")


if __name__ == "__main__":
    main()