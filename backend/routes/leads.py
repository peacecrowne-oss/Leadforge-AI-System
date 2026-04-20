"""Lead search API routes for LeadForge.

Defines an APIRouter that is registered in main.py via app.include_router().
Contains the four lead endpoints and their private row-to-model helpers.

Imports:
  models    → Pydantic types (no project cycle)
  state     → shared JOBS/RESULTS dicts (no project cycle)
  db.sqlite → persistence helpers (no project cycle)
  services  → business logic (no project cycle)
"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from datetime import datetime, timezone
import json
import csv
import io
import logging
import uuid

logger = logging.getLogger(__name__)

from models import LeadSearchRequest, Lead, SearchJob
from services.search_service import simulate_provider_search
from services.apollo_service import fetch_apollo_leads
from services.scoring_service import score_lead
from services.lead_pipeline_service import run_pipeline
from services.lead_message_service import send_message_to_leads
from auth.dependencies import get_current_user
from core.feature_flags import get_plan_features
from db.sqlite import db_connect, db_save_job, db_get_job, db_load_results, db_save_results, db_get_variants_for_leads
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


# ── Background task ───────────────────────────────────────────────────────────

def _run_google_pipeline(job_id: str, request: LeadSearchRequest, user_id: str) -> None:
    """Run the Google Places pipeline and sync results into JOBS/RESULTS for polling."""
    try:
        print("[BG TASK] STARTED")
        run_pipeline(
            query=request.keywords or "",
            location=request.location or "",
            user_id=user_id,
            job_id=job_id,
        )
        # Sync persisted results into the in-memory cache so polling can read them.
        RESULTS[job_id] = _leads_from_rows(db_load_results(job_id))
        row = db_get_job(job_id, user_id)
        if row:
            JOBS[job_id] = _job_from_row(row)
        # Explicitly stamp status and result count from live data.
        JOBS[job_id] = JOBS[job_id].model_copy(update={
            "status":        "complete",
            "results_count": len(RESULTS[job_id]),
            "updated_at":    datetime.now(timezone.utc),
        })
        print("[BG TASK] COMPLETED")
    except Exception as exc:
        print("[BG TASK ERROR]:", str(exc))
        logger.error("Google pipeline failed for job %s: %s", job_id, exc)
        now = datetime.now(timezone.utc)
        if job_id in JOBS:
            JOBS[job_id] = JOBS[job_id].model_copy(
                update={"status": "failed", "updated_at": now, "error": str(exc)}
            )
        raise


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

    background_tasks.add_task(_run_google_pipeline, job_id, request, current_user["user_id"])
    return {"job_id": job_id}


@router.post("/search-nlp", status_code=202)
def search_leads_nlp(request: LeadSearchRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Natural-language lead search — parses the keywords field before running the pipeline."""
    from services.lead_discovery_service import parse_natural_query

    raw_query = request.keywords or getattr(request, "query", "") or ""
    print(f"[NLP ROUTE] raw_query='{raw_query}'")
    parsed_query = parse_natural_query(raw_query)
    print(f"[NLP ROUTE] raw='{raw_query}' → parsed='{parsed_query}'")

    # Substitute parsed query into a copy of the request so location/company/limit are preserved.
    nlp_request = request.model_copy(update={"keywords": parsed_query})

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    JOBS[job_id] = SearchJob(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        request=nlp_request,
    )
    RESULTS[job_id] = []
    JOB_OWNERS[job_id] = current_user["user_id"]
    db_save_job(JOBS[job_id], user_id=current_user["user_id"])

    background_tasks.add_task(_run_google_pipeline, job_id, nlp_request, current_user["user_id"])
    return {"job_id": job_id}


@router.get("/leads/jobs")
def list_jobs(current_user: dict = Depends(get_current_user)):
    """Return all jobs owned by the current user, newest first."""
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT job_id, status, results_count, created_at
            FROM jobs
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (current_user["user_id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/leads/jobs/latest")
def get_latest_job(current_user: dict = Depends(get_current_user)):
    """Return the most recent job for the current user."""
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT job_id, status, created_at, results_count
            FROM jobs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (current_user["user_id"],),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No jobs found")
    return {
        "job_id":       row["job_id"],
        "status":       row["status"],
        "created_at":   row["created_at"],
        "result_count": row["results_count"],
    }


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

    variants = db_get_variants_for_leads([lead.id for lead in paged])
    paged = [lead.model_copy(update={"variant": variants.get(lead.id)}) for lead in paged]

    message = "Hi, are you open to a quick chat?"
    enriched_results = send_message_to_leads(paged, message)

    return {
        "job_id": job_id,
        "results": enriched_results,
        "count": len(all_results),
        "offset": offset,
        "limit": limit,
    }


@router.post("/leads/import/apollo", status_code=201)
def import_apollo_leads(
    request: LeadSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """Fetch leads from Apollo.io and store them as a completed search job.

    Synchronous — Apollo returns results in one HTTP call, so no background
    task is needed. The job is written with status='complete' immediately.
    The resulting job_id can be used with the standard /jobs/{id}/results
    and /jobs/{id}/export.csv endpoints without any changes.
    """
    user_id = current_user["user_id"]

    # ── Call Apollo ───────────────────────────────────────────────────────────
    try:
        raw_leads = fetch_apollo_leads({
            "keywords": request.keywords,
            "title":    request.title,
            "location": request.location,
            "company":  request.company,
            "limit":    request.limit,
        })
    except ValueError as exc:
        # Missing API key or bad configuration — caller's fault.
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        # Apollo returned an error or network failed — upstream fault.
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Normalise apollo dicts → Lead models and score each ───────────────────
    leads: list[Lead] = []
    for raw in raw_leads:
        lead = Lead(
            id=str(uuid.uuid4()),
            full_name=raw.get("name") or "Unknown",
            title=raw.get("title"),
            company=raw.get("company"),
            location=raw.get("location"),
            email=raw.get("email"),
        )
        computed_score, explanation = score_lead(lead, request)
        leads.append(lead.model_copy(update={
            "score": computed_score,
            "score_explanation": explanation,
        }))

    # ── Create a completed job and persist ────────────────────────────────────
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    job = SearchJob(
        job_id=job_id,
        status="complete",
        created_at=now,
        updated_at=now,
        request=request,
        results_count=len(leads),
    )

    JOBS[job_id] = job
    RESULTS[job_id] = leads
    JOB_OWNERS[job_id] = user_id

    db_save_job(job, user_id=user_id)
    db_save_results(job_id, leads)

    return {
        "job_id":   job_id,
        "imported": len(leads),
        "sample":   leads[:3],
    }


@router.post("/leads/import/csv", status_code=201)
def import_csv_leads(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Parse an uploaded CSV file and store the rows as a completed search job.

    Expected CSV columns (case-insensitive, extra columns ignored):
        Name, Title, Company, Email, Location

    The job is written with status='complete' immediately — no background task.
    The resulting job_id works with /jobs/{id}/results and /jobs/{id}/export.csv
    without any changes to those endpoints.
    """
    user_id = current_user["user_id"]

    # ── Read and decode the uploaded file ────────────────────────────────────
    raw_bytes = file.file.read()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    # Normalise header names to lowercase so "Name", "name", "NAME" all work.
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no header row.")
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    # ── Parse rows → Lead models ──────────────────────────────────────────────
    # An empty LeadSearchRequest gives neutral (0.5) scores for all filter
    # factors; seniority from the job title still ranks leads meaningfully.
    score_context = LeadSearchRequest()
    leads: list[Lead] = []

    # Query existing emails from DB once before the loop (cross-import dedup).
    with db_connect() as conn:
        db_rows = conn.execute(
            "SELECT DISTINCT lower(trim(email)) FROM job_leads WHERE email IS NOT NULL"
        ).fetchall()
    existing_emails: set[str] = {r[0] for r in db_rows}

    # Tracks emails seen within this CSV (within-file dedup).
    seen_emails: set[str] = set()
    skipped = 0
    row_num = 0

    for row in reader:
        row_num += 1
        logger.debug("Row %d raw: %s", row_num, dict(row))

        # Skip repeated header rows embedded in the file body.
        if row.get("first name") == "first name" or row.get("email") == "email":
            logger.debug("Row %d skipped: repeated header row", row_num)
            continue

        # Name: Apollo exports "First Name" / "Last Name"; generic exports use "Name".
        first = (row.get("first name") or "").strip()
        last  = (row.get("last name")  or "").strip()
        if first or last:
            name = " ".join(part for part in [first, last] if part)
        else:
            name = (row.get("name") or "").strip()

        # Skip rows where no name could be resolved at all.
        if not name:
            logger.debug("Row %d skipped: no name found (first=%r last=%r name=%r)",
                         row_num, first, last, row.get("name"))
            continue

        # Company: Apollo uses "Company Name"; generic exports use "Company".
        company = (
            (row.get("company name") or row.get("company") or "").strip() or None
        )

        # Location: Apollo provides city and state separately; generic exports
        # provide a single "Location" column.
        city  = (row.get("company city")  or "").strip()
        state = (row.get("company state") or "").strip()
        if city or state:
            location = ", ".join(part for part in [city, state] if part)
        else:
            location = (row.get("location") or "").strip() or None

        title = (row.get("title") or "").strip() or None
        email = (row.get("email") or "").strip().lower() or None

        # Dedup: skip if email seen in this file or already in the DB.
        # Leads with no email cannot be deduped — allow them through.
        if email:
            if email in seen_emails:
                logger.debug("Row %d skipped: duplicate email within file (%s)", row_num, email)
                skipped += 1
                continue
            if email in existing_emails:
                logger.debug("Row %d skipped: email already in DB (%s)", row_num, email)
                skipped += 1
                continue
            seen_emails.add(email)

        lead = Lead(
            id=str(uuid.uuid4()),
            full_name=name or "Unknown",
            title=title,
            company=company,
            email=email,
            location=location,
        )
        computed_score, explanation = score_lead(lead, score_context)
        leads.append(lead.model_copy(update={
            "score": computed_score,
            "score_explanation": explanation,
        }))
        logger.debug("Row %d accepted: name=%r email=%r", row_num, name, email)

    logger.info("CSV import complete — total rows: %d, inserted: %d, skipped: %d",
                row_num, len(leads), skipped)

    if not leads:
        raise HTTPException(status_code=422, detail="No valid lead rows found in the CSV.")

    # ── Create a completed job and persist ────────────────────────────────────
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    job = SearchJob(
        job_id=job_id,
        status="complete",
        created_at=now,
        updated_at=now,
        request=score_context,
        results_count=len(leads),
    )

    JOBS[job_id] = job
    RESULTS[job_id] = leads
    JOB_OWNERS[job_id] = user_id

    db_save_job(job, user_id=user_id)
    db_save_results(job_id, leads)

    return {
        "job_id":   job_id,
        "imported": len(leads),
        "skipped":  skipped,
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
