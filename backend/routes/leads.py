"""Lead search API routes for LeadForge.

Defines an APIRouter that is registered in main.py via app.include_router().
Contains the four lead endpoints and their private row-to-model helpers.

Imports:
  models    → Pydantic types (no project cycle)
  state     → shared JOBS/RESULTS dicts (no project cycle)
  db.sqlite → persistence helpers (no project cycle)
  services  → business logic (no project cycle)
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from datetime import datetime, timezone
import json
import csv
import io
import uuid

from models import LeadSearchRequest, Lead, SearchJob
from services.search_service import simulate_provider_search
from auth.dependencies import get_current_user
from core.feature_flags import get_plan_features
from db.sqlite import db_save_job, db_get_job, db_load_results
from state import JOBS, JOB_OWNERS, RESULTS

router = APIRouter()


# ── Private row → model helpers ───────────────────────────────────────────────

def _job_from_row(row: dict) -> SearchJob:
    """Construct a SearchJob from a raw db_load_job() dict."""
    return SearchJob(
        job_id=row["job_id"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        request=LeadSearchRequest(**json.loads(row["request_json"])),
        results_count=row["results_count"],
        error=row["error"],
    )


def _leads_from_rows(rows: list[dict]) -> list[Lead]:
    """Construct Lead instances from raw db_load_results() dicts."""
    return [Lead(**row) for row in rows]


def _get_owned_job(job_id: str, user_id: str) -> SearchJob:
    """Return the job if owned by user_id (or legacy un-owned); raise 404 otherwise.

    Checks the in-memory JOBS cache first. On a cache miss, falls back to a
    user-scoped SQLite query (db_get_job) and populates the cache on success.
    Raises HTTP 404 for both "not found" and "wrong owner" to avoid leaking
    whether a job exists for a different user.
    """
    if job_id in JOBS:
        owner = JOB_OWNERS.get(job_id)  # None = legacy row, accessible to all
        if owner is not None and owner != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return JOBS[job_id]

    row = db_get_job(job_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _job_from_row(row)
    JOBS[job_id] = job
    JOB_OWNERS[job_id] = row.get("user_id")
    return job


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/leads/search", status_code=202)
def create_search_job(request: LeadSearchRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Create a lead search job and queue the simulation in the background."""
    plan = current_user.get("plan", "free")
    features = get_plan_features(plan)
    search_limit = features["lead_search_limit"]
    if isinstance(search_limit, int) and request.limit > search_limit:
        request = request.model_copy(update={"limit": search_limit})

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    JOBS[job_id] = SearchJob(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        request=request,
    )
    RESULTS[job_id] = []
    JOB_OWNERS[job_id] = current_user["user_id"]
    # Persist immediately so the job survives a restart even if queued.
    db_save_job(JOBS[job_id], user_id=current_user["user_id"])

    # JOBS and RESULTS are passed into the service to avoid circular imports.
    background_tasks.add_task(simulate_provider_search, job_id, JOBS, RESULTS)
    return {"job_id": job_id}


@router.get("/leads/jobs/{job_id}", response_model=SearchJob)
def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Return the status and metadata of a lead search job owned by the current user."""
    return _get_owned_job(job_id, current_user["user_id"])


@router.get("/leads/jobs/{job_id}/results")
def get_job_results(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Return leads for a completed search job with pagination and stable ordering.

    Sorted by score descending (None treated as 0.0), then full_name ascending.
    `count` is always the total number of results, not the page size.
    Falls back to SQLite if the job or results are not in the in-memory cache.
    """
    _get_owned_job(job_id, current_user["user_id"])  # 404 if not found or not owned

    if job_id not in RESULTS:
        RESULTS[job_id] = _leads_from_rows(db_load_results(job_id))

    all_results = RESULTS.get(job_id, [])

    sorted_results = sorted(
        all_results,
        key=lambda lead: (-(lead.score or 0.0), lead.full_name),
    )

    paged = sorted_results[offset : offset + limit]

    return {
        "job_id": job_id,
        "results": paged,
        "count": len(all_results),
        "offset": offset,
        "limit": limit,
    }


@router.get("/leads/jobs/{job_id}/export.csv")
def export_leads_csv(job_id: str, current_user: dict = Depends(get_current_user)):
    """Export all leads for a completed job as a CSV file download.

    Uses the same lookup and sort order as /results (score desc, full_name asc).
    Returns 404 if the job does not exist; 409 if the job is not yet complete.
    """
    # ── Job lookup: owned by current user ────────────────────────────────────
    job = _get_owned_job(job_id, current_user["user_id"])  # 404 if not found or not owned
    if job.status != "complete":
        raise HTTPException(status_code=409, detail="Job not complete")

    # ── Results lookup ────────────────────────────────────────────────────────
    if job_id not in RESULTS:
        RESULTS[job_id] = _leads_from_rows(db_load_results(job_id))

    sorted_results = sorted(
        RESULTS.get(job_id, []),
        key=lambda lead: (-(lead.score or 0.0), lead.full_name),
    )

    # ── Build CSV in memory ───────────────────────────────────────────────────
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "full_name", "title", "company", "location",
                     "email", "linkedin_url", "score"])
    for lead in sorted_results:
        writer.writerow([
            lead.id,
            lead.full_name,
            lead.title or "",
            lead.company or "",
            lead.location or "",
            lead.email or "",
            lead.linkedin_url or "",
            lead.score if lead.score is not None else "",
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="leads_{job_id}.csv"'},
    )
