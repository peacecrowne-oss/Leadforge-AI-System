"""Read-only experiment routes for the A/B testing framework.

Endpoints (all require a valid JWT):
  GET /experiments                         — list all experiments (no variants)
  GET /experiments/{experiment_id}         — one experiment with variants
  GET /experiments/{experiment_id}/metrics — per-variant metrics
  GET /experiments/{experiment_id}/winner  — winner evaluation
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)
from db import db_get_experiment_metrics
from db.sqlite import db_connect
from models import (
    ExperimentResponse,
    ExperimentVariantMetrics,
    ExperimentVariantResponse,
    ExperimentWinnerResponse,
)
from services.experiment_service import evaluate_winner

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _load_experiment(experiment_id: str) -> dict | None:
    """Return an experiment row dict, or None if not found."""
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, name, description, status, created_at "
            "FROM experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()
    return dict(row) if row else None


def _load_variants(experiment_id: str) -> list[dict]:
    """Return variant rows for an experiment, ordered by creation time."""
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, experiment_id, name, traffic_percentage, created_at "
            "FROM experiment_variants "
            "WHERE experiment_id = ? "
            "ORDER BY created_at ASC, id ASC",
            (experiment_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(user: dict = Depends(get_current_user)):
    logger.info("experiments_list user_id=%s", user["user_id"])
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, name, description, status, created_at "
            "FROM experiments ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: str, user: dict = Depends(get_current_user)):
    logger.info(
        "experiment_detail experiment_id=%s user_id=%s",
        experiment_id,
        user["user_id"],
    )
    experiment = _load_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    experiment["variants"] = [
        ExperimentVariantResponse(**v) for v in _load_variants(experiment_id)
    ]
    return experiment


@router.get("/{experiment_id}/metrics", response_model=list[ExperimentVariantMetrics])
def get_experiment_metrics(experiment_id: str, user: dict = Depends(get_current_user)):
    logger.info(
        "experiment_metrics experiment_id=%s user_id=%s",
        experiment_id,
        user["user_id"],
    )
    if _load_experiment(experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return db_get_experiment_metrics(experiment_id)


@router.get("/{experiment_id}/winner", response_model=ExperimentWinnerResponse)
def get_experiment_winner(experiment_id: str, user: dict = Depends(get_current_user)):
    logger.info(
        "experiment_winner experiment_id=%s user_id=%s",
        experiment_id,
        user["user_id"],
    )
    if _load_experiment(experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    metrics = [
        ExperimentVariantMetrics(**row)
        for row in db_get_experiment_metrics(experiment_id)
    ]
    return evaluate_winner(metrics)
