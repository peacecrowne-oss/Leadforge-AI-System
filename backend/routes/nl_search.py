"""Natural-language lead search route for LeadForge.

Endpoint:
    POST /leads/nl-search

Accepts a plain-text query, parses it into structured fields via
nl_search_service, then creates a standard background search job
identical to POST /leads/search. Returns job_id (pollable via
GET /leads/jobs/{job_id}) plus the parsed fields for client transparency.
"""
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends

from auth.dependencies import get_current_user
from db.sqlite import db_save_job
from models import LeadSearchRequest, NaturalLanguageSearchRequest, SearchJob
from services.nl_search_service import parse_query
from services.search_service import simulate_provider_search
from state import JOB_OWNERS, JOBS, RESULTS

router = APIRouter()


@router.post("/leads/nl-search", status_code=202)
def nl_search(
    body: NaturalLanguageSearchRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Parse a natural-language query and create a lead search job.

    Returns:
        job_id — pollable via GET /leads/jobs/{job_id}
        parsed — the structured fields extracted from the query
    """
    parsed = parse_query(body.query)
    request = LeadSearchRequest(**parsed)

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
    db_save_job(JOBS[job_id], user_id=current_user["user_id"])

    background_tasks.add_task(simulate_provider_search, job_id, JOBS, RESULTS)

    return {"job_id": job_id, "parsed": parsed}
