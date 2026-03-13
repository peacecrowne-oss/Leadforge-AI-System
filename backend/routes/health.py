"""Metrics and system health endpoints."""
import logging

from fastapi import APIRouter

from core.metrics import get_metrics

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics")
def metrics():
    logger.info("metrics_requested")
    return get_metrics()


@router.get("/system/health")
def system_health():
    logger.info("system_health_check")
    return {"status": "ok", "service": "leadforge-api"}
