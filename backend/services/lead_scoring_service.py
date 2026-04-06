"""
lead_scoring_service.py

Wraps the existing deterministic score_lead() for use in the pipeline.
Converts plain lead dicts + an optional context dict into the typed objects
score_lead() expects, then attaches the result back onto the lead.

Does NOT mutate input. Does NOT connect to DB.
"""
import uuid

from models import Lead, LeadSearchRequest
from services.scoring_service import score_lead


def score_leads(leads: list[dict], context: dict | None = None) -> list[dict]:
    """
    Score each lead using the existing deterministic scoring engine.

    Args:
        leads:   List of lead dicts (output of normalize/enrich steps).
        context: Optional dict with scoring context keys:
                   keywords, title, location, company, limit
                 Maps directly to LeadSearchRequest fields.
                 Pass None (or {}) for context-free scoring.

    Returns:
        A new list of lead dicts, each with two extra keys added:
          score             – float in [0.0, 1.0]
          score_explanation – dict mapping factor name → weighted contribution
    """
    ctx = context or {}
    request = LeadSearchRequest(
        keywords=ctx.get("keywords"),
        title=ctx.get("title"),
        location=ctx.get("location"),
        company=ctx.get("company"),
    )

    scored = []
    for lead in leads:
        lead_obj = Lead(
            id=lead.get("id") or str(uuid.uuid4()),
            full_name=lead.get("full_name") or "",
            title=lead.get("title"),
            company=lead.get("company"),
            location=lead.get("location"),
            email=lead.get("email"),
        )

        score, explanation = score_lead(lead_obj, request)

        updated = dict(lead)
        updated["score"] = score
        updated["score_explanation"] = explanation
        scored.append(updated)

    return scored
