"""JWT encode/decode utilities.

Algorithm : HS256 (HMAC-SHA-256) via python-jose.
Claims always present in every token:
  sub — subject (user id string)
  iat — issued-at  (UTC, integer epoch seconds)
  exp — expiry     (UTC, iat + expires_minutes)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jose import jwt

ALGORITHM = "HS256"


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
