"""System / health check routes for LeadForge.

Defines an APIRouter with the root and health endpoints.
No authentication required on any route here.
"""
import logging

from fastapi import APIRouter

from db.sqlite import db_connect

logger = logging.getLogger(__name__)

router = APIRouter()

_API_VERSION = "1.0.0"


@router.get("/")
def read_root():
    return {"message": "LeadForge AI Backend Running"}


@router.get("/health")
def health_check():
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"

    logger.info("health_check db=%s", db_status)
    return {
        "status": "ok",
        "db": db_status,
        "version": _API_VERSION,
    }
