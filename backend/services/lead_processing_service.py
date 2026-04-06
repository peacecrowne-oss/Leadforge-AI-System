"""
lead_processing_service.py

Extraction and normalization layer.
Converts raw lead dicts (from any source) into a consistent schema.
No database access, no external calls.
"""


def normalize_leads(raw_leads: list[dict]) -> list[dict]:
    """
    Normalize a list of raw lead dicts into a consistent schema.

    Each output dict contains:
        full_name : str   – whitespace-stripped
        company   : str   – whitespace-stripped
        title     : str   – whitespace-stripped
        location  : str   – whitespace-stripped
        website   : str   – whitespace-stripped, lowercased
        email     : None  – placeholder; not populated at this stage

    Missing fields default to "" (or None for email).
    """
    normalized = []
    for raw in raw_leads:
        def _str(key: str) -> str:
            value = raw.get(key, "")
            return (value or "").strip()

        normalized.append({
            "full_name": _str("full_name"),
            "company":   _str("company"),
            "title":     _str("title"),
            "location":  _str("location"),
            "website":   _str("website").lower(),
            "email":     None,
        })
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
