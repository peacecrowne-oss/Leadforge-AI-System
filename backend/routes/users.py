"""User data endpoints for GDPR / CCPA compliance.

Endpoints (all require a valid JWT):
  GET    /users/me/data    — return all data held for the authenticated user
  GET    /users/me/export  — same data as a downloadable JSON attachment
  DELETE /users/me         — permanently delete the user and all associated data
"""
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth.dependencies import get_current_user
from db.sqlite import db_connect
from models import UserDataExport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


def _collect_user_data(user_id: str) -> dict:
    """Return all stored data for *user_id* as a plain dict."""
    with db_connect() as conn:
        user_row = conn.execute(
            "SELECT user_id, email, role, plan, consent_given, consent_timestamp, created_at "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        campaign_rows = conn.execute(
            "SELECT id, name, status, created_at FROM campaigns WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        job_rows = conn.execute(
            "SELECT job_id, status, query, created_at FROM search_jobs WHERE user_id = ?",
            (user_id,),
        ).fetchall()

    return {
        "user": dict(user_row) if user_row else {},
        "campaigns": [dict(r) for r in campaign_rows],
        "search_jobs": [dict(r) for r in job_rows],
    }


@router.get("/me/data", response_model=UserDataExport)
def get_my_data(user: dict = Depends(get_current_user)) -> dict:
    user_id = user["user_id"]
    logger.info("user_data_requested user_id=%s", user_id)
    return _collect_user_data(user_id)


@router.get("/me/export")
def export_my_data(user: dict = Depends(get_current_user)) -> Response:
    user_id = user["user_id"]
    logger.info("user_data_exported user_id=%s", user_id)
    data = _collect_user_data(user_id)
    content = json.dumps(data, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="leadforge_user_export.json"'},
    )


@router.delete("/me", status_code=200)
def delete_my_account(user: dict = Depends(get_current_user)) -> dict:
    user_id = user["user_id"]
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM experiment_variant_events WHERE campaign_id IN "
            "(SELECT id FROM campaigns WHERE user_id = ?)",
            (user_id,),
        )
        conn.execute("DELETE FROM campaigns WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM search_jobs WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    logger.info("user_account_deleted user_id=%s", user_id)
    return {"message": "User account and associated data deleted"}
