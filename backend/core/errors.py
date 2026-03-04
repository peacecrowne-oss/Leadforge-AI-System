"""Standardized error response handlers for LeadForge.

All API errors are returned in the envelope:

    {
        "error": {
            "code":    "<ERROR_CODE>",
            "message": "<human-readable message>",
            "details": <optional, field-level info for 422>
        }
    }

Handlers are registered in main.py via app.add_exception_handler().
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Maps HTTP status codes to stable machine-readable error code strings.
_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


def _error_body(code: str, message: str, details: Any = None) -> dict:
    """Build the standardized error envelope."""
    payload: dict = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"error": payload}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert HTTPException into the standard error envelope.

    Preserves any extra headers set by the exception (e.g. WWW-Authenticate
    on 401 responses from the OAuth2 dependency).
    """
    code = _HTTP_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, str(exc.detail)),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI's 422 RequestValidationError into the standard envelope.

    Field-level error details (loc, msg, type) are included under "details"
    so clients can map errors back to specific request fields.
    """
    return JSONResponse(
        status_code=422,
        content=_error_body(
            "VALIDATION_ERROR",
            "Request validation failed",
            details=exc.errors(),
        ),
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unexpected exceptions.

    Logs the full traceback server-side (via logging.exception) but returns
    only a generic message to the client — no stack traces are leaked.
    """
    logger.exception("Unhandled exception: %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "An internal server error occurred"),
    )
