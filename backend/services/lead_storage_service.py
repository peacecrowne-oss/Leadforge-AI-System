"""
lead_storage_service.py

Persists pipeline-processed leads into the existing job_leads table.

Schema mapping
--------------
job_leads column  ← pipeline field
-----------------   ----------------
job_id            ← generated: "pipeline_<user_id>_<uuid>"
lead_id           ← lead["id"]  (generated if missing)
full_name         ← lead["full_name"]
title             ← lead["title"]
company           ← lead["company"]
location          ← lead["location"]
email             ← lead["email"]
score             ← lead["score"]
linkedin_url      ← JSON blob: {"website": ..., "score_explanation": ...}
                     (no separate columns exist for these fields without a
                      schema change, so they are packed here as structured JSON)

Duplicates: rows with the same (job_id, lead_id) PRIMARY KEY are skipped via
INSERT OR IGNORE.

Does NOT change the schema. Does NOT modify existing routes.
"""
import json
import uuid

from db.sqlite import db_connect


def store_leads(leads: list[dict], user_id: str) -> int:
    """
    Persist a list of pipeline leads for a given user.

    A synthetic job_id is generated per call so each batch is isolated.

    Args:
        leads:   List of enriched/scored lead dicts.
        user_id: ID of the owning user.

    Returns:
        Number of leads actually inserted (duplicates are skipped).
    """
    job_id = f"pipeline_{user_id}_{uuid.uuid4()}"
    now = __import__("datetime").datetime.utcnow().isoformat()

    rows = []
    for lead in leads:
        lead_id   = lead.get("id") or str(uuid.uuid4())
        full_name = (lead.get("full_name") or "").strip()
        title     = lead.get("title")
        company   = lead.get("company")
        location  = lead.get("location")
        email     = lead.get("email")
        score     = lead.get("score")

        # Pack fields that have no dedicated column into a JSON blob.
        extra = {}
        if lead.get("website"):
            extra["website"] = lead["website"]
        if lead.get("score_explanation"):
            extra["score_explanation"] = lead["score_explanation"]
        linkedin_url = json.dumps(extra) if extra else None

        rows.append((
            job_id, lead_id, full_name, title, company,
            location, email, linkedin_url, score,
        ))

    if not rows:
        return 0

    with db_connect() as conn:
        cursor = conn.executemany(
            """
            INSERT OR IGNORE INTO job_leads
                (job_id, lead_id, full_name, title, company,
                 location, email, linkedin_url, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return cursor.rowcount
