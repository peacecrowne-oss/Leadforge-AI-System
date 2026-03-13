"""Auth routes for LeadForge: user registration and JWT login.

Endpoints:
  POST /auth/register  — create account, returns public user dict (201)
  POST /auth/login     — OAuth2 password flow, returns bearer token
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from auth.hashing import hash_password, verify_password
from auth.jwt import create_access_token
from db.sqlite import db_connect, db_create_user, db_get_user_by_email, db_update_user_plan

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginJsonRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> dict:
    """Create a new user account.

    Normalizes email (strip + lowercase) before storage.
    Returns the created user record without hashed_password.
    Returns HTTP 409 if the email is already registered.
    """
    email = body.email.strip().lower()
    hashed = hash_password(body.password)
    try:
        user = db_create_user(email=email, hashed_password=hashed)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    consent_ts = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "UPDATE users SET consent_given = 1, consent_timestamp = ? WHERE user_id = ?",
            (consent_ts, user["user_id"]),
        )
    return user


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    """Issue a JWT bearer token via OAuth2 password flow.

    The OAuth2 form field ``username`` is treated as the user's email address,
    matching the tokenUrl declared in auth/dependencies.py.

    Returns HTTP 401 on invalid email or password.
    Returns HTTP 500 if JWT_SECRET is not set in the environment (server
    misconfiguration — the client's credentials are not at fault).
    """
    secret_key = os.getenv("JWT_SECRET", "")
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error",
        )

    # form.username is the email (OAuth2 spec calls it 'username')
    user = db_get_user_by_email(form.username)
    if user is None or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=user["user_id"],
        secret_key=secret_key,
        expires_minutes=60,
        extra_claims={"email": user["email"], "role": user["role"], "plan": user.get("plan", "free")},
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login-json")
def login_json(body: LoginJsonRequest) -> dict:
    """Issue a JWT bearer token via JSON body (email + password).

    Accepts ``Content-Type: application/json`` with ``{"email": ..., "password": ...}``.
    Normalizes email before lookup.

    Returns HTTP 401 on invalid email or password.
    Returns HTTP 500 if JWT_SECRET is not set in the environment.
    """
    secret_key = os.getenv("JWT_SECRET", "")
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error",
        )

    email = body.email.strip().lower()
    user = db_get_user_by_email(email)
    if user is None or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=user["user_id"],
        secret_key=secret_key,
        expires_minutes=60,
        extra_claims={"email": user["email"], "role": user["role"], "plan": user.get("plan", "free")},
    )
    return {"access_token": token, "token_type": "bearer"}


# DEV ONLY
class DevUpgradeRequest(BaseModel):
    email: str
    plan: str


_VALID_PLANS = {"free", "pro", "enterprise"}


@router.post("/dev-upgrade")
def dev_upgrade(body: DevUpgradeRequest) -> dict:
    """Upgrade a user's plan for local testing.

    # DEV ONLY — not guarded by auth; do not expose in production.
    """
    if body.plan not in _VALID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid plan. Must be one of: {sorted(_VALID_PLANS)}",
        )
    updated = db_update_user_plan(body.email, body.plan)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "email": updated["email"],
        "plan": updated["plan"],
        "message": "User upgraded successfully",
    }
