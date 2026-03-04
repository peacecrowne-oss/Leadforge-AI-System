"""FastAPI auth dependencies.

Usage in a route:

    from auth.dependencies import get_current_user

    @router.get("/me")
    def me(user: dict = Depends(get_current_user)):
        return user

Environment variables required at runtime:
    JWT_SECRET — HMAC signing secret for JWTs (must be set; no default in
                 production).  The dependency raises HTTP 401 if unset so
                 the app fails safely rather than silently accepting tokens
                 signed with an empty key.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from auth.jwt import decode_token
from db.sqlite import db_get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validate a bearer token and return the corresponding user row dict.

    Steps:
      1. Read JWT_SECRET from the environment (HTTP 401 if unset).
      2. Decode and verify the JWT; raise HTTP 401 on any JWTError.
      3. Extract ``sub`` as user_id; raise HTTP 401 if absent.
      4. Look up the user in the DB; raise HTTP 401 if not found.

    Returns:
        A plain dict representing the user row (same shape returned by
        db_get_user_by_id).

    Raises:
        HTTP 401: For any of the failure conditions above.
    """
    secret_key = os.getenv("JWT_SECRET", "")
    if not secret_key:
        raise _CREDENTIALS_EXCEPTION

    try:
        payload = decode_token(token, secret_key)
        user_id: str | None = payload.get("sub")
    except JWTError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    if not user_id:
        raise _CREDENTIALS_EXCEPTION

    user = db_get_user_by_id(user_id)
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    return user
