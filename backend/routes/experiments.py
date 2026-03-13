"""Experiment routes for the A/B testing framework.

Endpoints (all require a valid JWT):
  POST /experiments                        — create an experiment
  GET  /experiments                        — list all experiments (no variants)
  GET  /experiments/{experiment_id}        — one experiment with variants
  GET  /experiments/{experiment_id}/metrics — per-variant metrics
  GET  /experiments/{experiment_id}/winner  — winner evaluation
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from core.feature_flags import get_plan_features
from db import db_get_experiment_metrics
from db.sqlite import db_connect
from models import (
    ExperimentCreate,
    ExperimentResponse,
    ExperimentVariantCreate,
    ExperimentVariantMetrics,
    ExperimentVariantResponse,
    ExperimentWinnerResponse,
)
from services.experiment_service import evaluate_winner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experiments", tags=["experiments"])

_EXPERIMENTS_403 = HTTPException(
    status_code=403,
    detail="Experiments require Enterprise plan",
)


def _check_experiments_access(user: dict) -> None:
    if not get_plan_features(user.get("plan", "free"))["experiments"]:
        raise _EXPERIMENTS_403


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


@router.post("", status_code=201, response_model=ExperimentResponse)
def create_experiment(body: ExperimentCreate, user: dict = Depends(get_current_user)):
    _check_experiments_access(user)
    experiment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO experiments (id, name, description, status, created_at) "
            "VALUES (?, ?, ?, 'draft', ?)",
            (experiment_id, body.name, body.description, now),
        )
    logger.info(
        "experiment_created experiment_id=%s user_id=%s",
        experiment_id,
        user["user_id"],
    )
    return {
        "id": experiment_id,
        "name": body.name,
        "description": body.description,
        "status": "draft",
        "created_at": now,
        "variants": [],
    }


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(user: dict = Depends(get_current_user)):
    _check_experiments_access(user)
    logger.info("experiments_list user_id=%s", user["user_id"])
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, name, description, status, created_at "
            "FROM experiments ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: str, user: dict = Depends(get_current_user)):
    _check_experiments_access(user)
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
    _check_experiments_access(user)
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
    _check_experiments_access(user)
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


@router.post("/{experiment_id}/variants", status_code=201, response_model=ExperimentVariantResponse)
def create_variant(experiment_id: str, body: ExperimentVariantCreate, user: dict = Depends(get_current_user)):
    _check_experiments_access(user)
    if _load_experiment(experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    variant_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with db_connect() as conn:
        conn.execute(
            "INSERT INTO experiment_variants "
            "(id, experiment_id, name, traffic_percentage, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (variant_id, experiment_id, body.name, body.traffic_percentage, now),
        )

    logger.info(
        "experiment_variant_created experiment_id=%s variant_id=%s user_id=%s",
        experiment_id,
        variant_id,
        user["user_id"],
    )

    return {
        "id": variant_id,
        "experiment_id": experiment_id,
        "name": body.name,
        "traffic_percentage": body.traffic_percentage,
        "created_at": now,
    }


@router.post("/{experiment_id}/start", response_model=ExperimentResponse)
def start_experiment(experiment_id: str, user: dict = Depends(get_current_user)):
    _check_experiments_access(user)

    with db_connect() as conn:
        conn.execute(
            "UPDATE experiments SET status = 'running' WHERE id = ?",
            (experiment_id,),
        )
        row = conn.execute(
            "SELECT id, name, description, status, created_at "
            "FROM experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    logger.info(
        "experiment_started experiment_id=%s user_id=%s",
        experiment_id,
        user["user_id"],
    )

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "created_at": row["created_at"],
        "variants": [],
    }
