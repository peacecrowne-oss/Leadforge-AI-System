"""Structured logging for LeadForge backend.

Two public symbols:

    configure_logging()  — call once at startup to configure the root logger.
    LoggingMiddleware    — Starlette BaseHTTPMiddleware that emits one
                          structured key=value log line per request and stamps
                          X-Request-Id on every response.

Log format (single line, no JSON):
    2026-03-04T12:00:00 INFO  core.logging request_end \
        request_id=<uuid> method=GET path=/health status=200 duration_ms=3 \
        [user_id=<uuid> email=user@example.com]

User context is appended only when a valid Bearer token is present and
JWT_SECRET is set.  The token string itself is never logged.
"""
from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from typing import Callable

from fastapi import Request
from fastapi.responses import Response
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from auth.jwt import decode_token

logger = logging.getLogger(__name__)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a compact single-line format.

    Uses force=True (Python 3.8+) so repeated calls are safe and any
    handlers added before startup are cleared.  Writes to stdout so
    logs are visible in containerised and local environments alike.
    """
    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )


def _extract_user(request: Request) -> dict[str, str]:
    """Try to decode the bearer token and return user context fields.

    Returns a dict with 'user_id' and 'email' on success; an empty dict on
    any failure (missing Authorization header, missing JWT_SECRET, expired or
    malformed token).  Never raises.  Never exposes the token string.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return {}

    token = auth[7:]  # strip "Bearer " prefix — token itself is not logged
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        return {}

    try:
        payload = decode_token(token, secret)
    except (JWTError, Exception):
        return {}

    user_id: str = payload.get("sub", "")
    if not user_id:
        return {}
    return {"user_id": user_id, "email": payload.get("email", "")}


class LoggingMiddleware(BaseHTTPMiddleware):
    """Per-request structured logging middleware.

    For every request:
      1. Accept X-Request-Id from the incoming header, or generate a UUID4.
      2. Store request_id on request.state (available to handlers/error loggers).
      3. Call the next layer and capture the response.
      4. Log one INFO line: request_end <key=value pairs>.
      5. Stamp X-Request-Id on the response before returning it.

    On truly unhandled exceptions that bubble up through call_next:
      - Log with logger.exception (includes stack trace).
      - Re-raise so ServerErrorMiddleware can produce the 500 response.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.exception(
                "request_error request_id=%s method=%s path=%s duration_ms=%d",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise  # ServerErrorMiddleware handles the 500

        duration_ms = round((time.monotonic() - start) * 1000)

        user_ctx = _extract_user(request)
        user_part = ""
        if user_ctx:
            user_part = (
                f" user_id={user_ctx['user_id']} email={user_ctx['email']}"
            )

        logger.info(
            "request_end request_id=%s method=%s path=%s status=%d duration_ms=%d%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            user_part,
        )

        response.headers["X-Request-Id"] = request_id
        return response
