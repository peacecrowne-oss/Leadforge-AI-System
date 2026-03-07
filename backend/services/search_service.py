"""Lead search service for LeadForge.

Contains all business logic for lead generation, deduplication, and the
background task that drives the provider search simulation.

Design constraints:
- No FastAPI imports; no route definitions.
- Imports models from models.py, persistence from db.sqlite, and scoring from services.scoring_service.
- JOBS and RESULTS dicts are received as parameters rather than imported
  from main.py, which avoids circular imports while keeping the stores
  in a single authoritative location (main.py).
"""
from datetime import datetime, timezone
import uuid
import time

from models import Lead, SearchJob
from db.sqlite import db_save_job, db_save_results
from services.scoring_service import score_lead


def dedupe_key(lead: Lead) -> str:
    """Return a stable identity key for a lead used to detect duplicates.

    Priority: email > linkedin_url > full_name|company fallback.
    All values are lowercased and stripped so minor formatting differences
    don't create false duplicates.
    """
    if lead.email:
        return lead.email.lower().strip()
    if lead.linkedin_url:
        return lead.linkedin_url.lower().strip()
    return f"{lead.full_name.lower()}|{lead.company.lower() if lead.company else ''}"


def simulate_provider_search(
    job_id: str,
    jobs: dict[str, SearchJob],
    results: dict[str, list[Lead]],
) -> None:
    """Simulate a lead search by generating deterministic mock leads.

    Uses request fields as seeds so the same query always yields the
    same shape of results. Caps output at request.limit.

    Args:
        job_id:  UUID of the job to run.
        jobs:    The shared in-memory JOBS store (mutated in-place).
        results: The shared in-memory RESULTS store (mutated in-place).
    """
    try:
        job = jobs[job_id]

        # Mark running
        jobs[job_id] = job.model_copy(
            update={"status": "running", "updated_at": datetime.now(timezone.utc)}
        )

        time.sleep(0.5)  # Simulate provider latency

        req = job.request
        seed_title = req.title or "Software Engineer"
        seed_company = req.company or "Acme Corp"
        seed_location = req.location or "San Francisco, CA"
        seed_keyword = req.keywords or "technology"

        # Pool of mock names – deterministic ordering
        mock_names = [
            "Alex Rivera", "Jordan Lee", "Morgan Chen", "Taylor Kim",
            "Casey Patel", "Jamie Okonkwo", "Riley Nakamura", "Avery Singh",
            "Quinn Ramirez", "Drew Hoffman", "Skyler Wu", "Reese Oduya",
            "Emery Vasquez", "Parker Zhao", "Sage Andersen",
        ]

        # 5–15 leads based on keyword length, capped by limit
        raw_count = (len(seed_keyword) % 11) + 5  # 5..15
        count = min(raw_count, req.limit)

        leads: list[Lead] = []
        for i, name in enumerate(mock_names[:count]):
            slug = name.lower().replace(" ", ".")
            lead = Lead(
                id=str(uuid.uuid4()),
                full_name=name,
                title=f"Senior {seed_title}" if i % 3 == 0 else seed_title,
                company=f"{seed_company} Inc." if i % 4 == 0 else seed_company,
                location=seed_location,
                email=f"{slug}@example.com",
                linkedin_url=f"https://linkedin.com/in/{slug}",
            )
            computed_score, explanation = score_lead(lead, req)
            leads.append(lead.model_copy(update={
                "score": computed_score,
                "score_explanation": explanation,
            }))

        # Deduplicate: sort desc by score first so the first occurrence of any
        # key is always the highest-scored version, then keep only unique keys.
        leads.sort(key=lambda l: -(l.score or 0.0))
        seen: set[str] = set()
        deduped: list[Lead] = []
        for lead in leads:
            key = dedupe_key(lead)
            if key not in seen:
                seen.add(key)
                deduped.append(lead)

        # Apply limit after dedupe so the stored count respects both constraints.
        deduped = deduped[: req.limit]

        results[job_id] = deduped
        jobs[job_id] = jobs[job_id].model_copy(
            update={
                "status": "complete",
                "results_count": len(deduped),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        # Persist final results and job state to SQLite.
        db_save_results(job_id, deduped)
        db_save_job(jobs[job_id])

    except Exception as exc:
        jobs[job_id] = jobs[job_id].model_copy(
            update={
                "status": "failed",
                "error": str(exc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        db_save_job(jobs[job_id])
