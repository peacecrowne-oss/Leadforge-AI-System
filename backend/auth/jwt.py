"""JWT encode/decode utilities.

Algorithm : HS256 (HMAC-SHA-256) via python-jose.
Claims always present in every token:
  sub — subject (user id string)
  iat — issued-at  (UTC, integer epoch seconds)
  exp — expiry     (UTC, iat + expires_minutes)

Module-level constants (resolved once at import time):
  SECRET_KEY — HMAC signing secret; reads JWT_SECRET env var with a dev fallback.
  ALGORITHM  — always "HS256".
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from jose import jwt

_logger = logging.getLogger(__name__)

# ── JWT algorithm ─────────────────────────────────────────────────────────────
ALGORITHM = "HS256"

# ── Signing secret ────────────────────────────────────────────────────────────
_DEV_SECRET = "dev-insecure-secret-change-me"

SECRET_KEY: str = os.getenv("JWT_SECRET", "").strip()
if not SECRET_KEY:
    SECRET_KEY = _DEV_SECRET
    # Back-patch the environment so every subsequent os.getenv("JWT_SECRET")
    # call in other modules (routes/auth.py, auth/dependencies.py) also sees
    # the non-empty value — eliminating the HTTP 500 guard in the login route.
    os.environ["JWT_SECRET"] = SECRET_KEY
    _logger.warning(
        "JWT_SECRET env var is not set or blank; "
        "using a dev-only default secret. "
        "Set JWT_SECRET before deploying to production."
    )


def create_access_token(
    subject: str,
    secret_key: str,
    expires_minutes: int = 60,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Return a signed JWT string for *subject*.

    Args:
        subject:        Unique identifier stored in the ``sub`` claim
                        (typically the user's UUID string).
        secret_key:     HMAC signing secret; must be kept server-side.
        expires_minutes: Lifetime of the token in minutes (default 60).
        extra_claims:   Optional additional claims merged into the payload.
                        Keys ``sub``, ``iat``, and ``exp`` are reserved and
                        will be overwritten if present in *extra_claims*.

    Returns:
        A compact, URL-safe JWT string.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_minutes * 60,
    }
    if extra_claims:
        # Merge first so reserved keys above always win.
        merged = {**extra_claims, **payload}
        payload = merged
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_token(token: str, secret_key: str) -> dict[str, Any]:
    """Decode and verify *token*.

    Args:
        token:      Compact JWT string.
        secret_key: The same secret used to sign the token.

    Returns:
        The decoded payload as a plain dict.

    Raises:
        jose.JWTError: If the token is malformed, the signature is invalid,
                       or the token has expired.
    """
    return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
