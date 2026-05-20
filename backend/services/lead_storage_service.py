"""
lead_storage_service.py

Persists pipeline-processed leads into the existing job_leads table.

Schema mapping
--------------
job_leads column  ← pipeline field
-----------------   ----------------
job_id            ← passed in by caller
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


def store_leads(leads: list[dict], user_id: str, job_id: str) -> int:
    """
    Persist a list of pipeline leads for a given user.

    Args:
        leads:   List of enriched/scored lead dicts.
        user_id: ID of the owning user.
        job_id:  Job ID to use for all inserted rows (must match the jobs table entry).

    Returns:
        Number of leads actually inserted (duplicates are skipped).
    """
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

        phone                 = lead.get("phone") or None
        address               = lead.get("address") or None
        domain                = lead.get("domain") or None
        confidence            = lead.get("confidence") or None
        reason                = lead.get("reason") or None
        fabricated_email      = 1 if lead.get("fabricated_email") else None
        provider              = lead.get("provider") or None
        provider_entity_type  = lead.get("provider_entity_type") or None
        provider_confidence   = lead.get("provider_confidence") or None
        phone_provider        = lead.get("phone_provider") or None
        email_provider        = lead.get("email_provider") or None
        domain_provider       = lead.get("domain_provider") or None
        address_provider      = lead.get("address_provider") or None
        contact_name          = lead.get("contact_name") or None
        contact_role          = lead.get("contact_role") or None
        contact_source        = lead.get("contact_source") or None
        contact_confidence    = lead.get("contact_confidence") or None
        identity_type         = lead.get("identity_type") or None

        rows.append((
            job_id, lead_id, full_name, title, company,
            location, email, linkedin_url, score,
            domain, confidence, reason, fabricated_email,
            provider, provider_entity_type, provider_confidence,
            phone_provider, email_provider, domain_provider, address_provider,
            phone, address,
            contact_name, contact_role, contact_source, contact_confidence,
            identity_type,
        ))

    print(f"[STORE] job_id={job_id} input_leads={len(leads)} rows_prepared={len(rows)}")
    if leads:
        _s = leads[0]
        print(
            f"[STORE] sample[0] full_name={_s.get('full_name')!r}"
            f" company={_s.get('company')!r}"
            f" email={_s.get('email')!r}"
            f" score={_s.get('score')}"
            f" provider={_s.get('provider')!r}"
            f" provider_entity_type={_s.get('provider_entity_type')!r}"
        )

    if not rows:
        print(f"[STORE] job_id={job_id} ABORTED — no rows to insert")
        return 0

    import time as _time
    with db_connect() as conn:
        _write_t0 = _time.perf_counter()
        cursor = conn.executemany(
            """
            INSERT OR IGNORE INTO job_leads
                (job_id, lead_id, full_name, title, company,
                 location, email, linkedin_url, score,
                 domain, confidence, reason, fabricated_email,
                 provider, provider_entity_type, provider_confidence,
                 phone_provider, email_provider, domain_provider, address_provider,
                 phone, address,
                 contact_name, contact_role, contact_source, contact_confidence,
                 identity_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        _write_ms = round((_time.perf_counter() - _write_t0) * 1000)
        print(f"[STORE] job_id={job_id} cursor.rowcount={cursor.rowcount} executemany_ms={_write_ms}")
        return cursor.rowcount
