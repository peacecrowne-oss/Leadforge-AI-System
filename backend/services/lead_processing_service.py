"""
lead_processing_service.py

Extraction and normalization layer.
Converts raw lead dicts (from any source) into a consistent schema.
No database access, no external calls.
"""


def normalize_leads(raw_leads: list[dict]) -> list[dict]:
    """
    Normalize a list of raw lead dicts into a consistent schema.

    Cleaning applied to known fields:
        full_name : str   – whitespace-stripped; derived from first/last if present
        company   : str   – whitespace-stripped
        title     : str   – whitespace-stripped
        location  : str   – whitespace-stripped
        website   : str   – whitespace-stripped, lowercased

    All other fields (domain, source, email, email_candidates, roles, etc.)
    are passed through from the input unchanged.  The function never builds a
    whitelist dict — it copies the full input and overwrites only the cleaned
    fields, so new fields added by any discovery service survive automatically.
    """
    normalized = []
    for raw in raw_leads:
        def _str(key: str) -> str:
            value = raw.get(key, "")
            return (value or "").strip()

        first = _str("first_name")
        last  = _str("last_name")
        if first or last:
            full_name = f"{first} {last}".strip()
        else:
            full_name = _str("full_name") or _str("company")

        lead = dict(raw)
        lead["full_name"] = full_name
        lead["company"]   = _str("company")
        lead["title"]     = _str("title")
        lead["location"]  = _str("location")
        lead["website"]   = _str("website").lower()
        normalized.append(lead)
    return normalized


def deduplicate_leads(leads: list[dict]) -> list[dict]:
    """
    Remove invalid and duplicate leads.

    A lead is invalid if full_name or company is empty and will be skipped.

    Duplicate detection uses:
      - email (lowercased) if non-empty
      - otherwise "full_name|company" (both lowercased)

    Returns a new list with only the first occurrence of each unique lead.
    """
    seen = set()
    result = []
    for lead in leads:
        full_name = (lead.get("full_name") or "").strip()
        company   = (lead.get("company")   or "").strip()

        # Skip invalid leads
        if not full_name or not company:
            continue

        email = (lead.get("email") or "").strip().lower()
        identifier = email if email else f"{full_name.lower()}|{company.lower()}"

        if identifier in seen:
            continue

        seen.add(identifier)
        result.append(lead)

    return result
