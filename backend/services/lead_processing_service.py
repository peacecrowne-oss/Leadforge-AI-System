"""
lead_processing_service.py

Extraction and normalization layer.
Converts raw lead dicts (from any source) into a consistent schema.
No database access, no external calls.
"""
import re as _re

# Tokens that strongly indicate a business name rather than a person name.
_BUSINESS_RE = _re.compile(
    r'\b(?:llc|inc|corp|ltd|restaurant|plumbing|dental|clinic|'
    r'services|solutions|group|associates|partners|company|enterprises|'
    r'consulting|construction|roofing|cleaning|landscaping|salon|'
    r'barbershop|auto|repair|bakery|cafe|realty|properties)\b',
    _re.IGNORECASE,
)
# Two or more capitalized proper-name tokens (e.g. "Jane Smith", "John A Lee").
_PERSON_RE = _re.compile(r'^[A-Z][a-z]+(?: [A-Z][a-z]+)+$')


def classify_identity(full_name: str | None) -> str:
    """Return 'person', 'business', or 'unknown' for a full_name string."""
    name = (full_name or '').strip()
    if not name:
        return 'unknown'
    if _BUSINESS_RE.search(name):
        return 'business'
    if _PERSON_RE.match(name):
        return 'person'
    return 'unknown'


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
        lead["full_name"]     = full_name
        lead["company"]       = _str("company")
        lead["title"]         = _str("title")
        lead["location"]      = _str("location")
        lead["website"]       = _str("website").lower()
        lead["identity_type"] = classify_identity(full_name)
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
    skipped_empty = 0
    skipped_dup   = 0

    if leads:
        _s = leads[0]
        print(
            f"[DEDUP] sample_in[0] full_name={_s.get('full_name')!r}"
            f" company={_s.get('company')!r}"
            f" email={_s.get('email')!r}"
            f" domain={_s.get('domain')!r}"
            f" source={_s.get('source')!r}"
        )

    for lead in leads:
        full_name = (lead.get("full_name") or "").strip()
        company   = (lead.get("company")   or "").strip()

        # Skip invalid leads
        if not full_name or not company:
            skipped_empty += 1
            if skipped_empty <= 3:
                print(
                    f"[DEDUP] DROP_EMPTY full_name={full_name!r}"
                    f" company={company!r}"
                    f" source={lead.get('source')!r}"
                )
            continue

        email = (lead.get("email") or "").strip().lower()
        identifier = email if email else f"{full_name.lower()}|{company.lower()}"

        if identifier in seen:
            skipped_dup += 1
            continue

        seen.add(identifier)
        result.append(lead)

    print(
        f"[DEDUP] in={len(leads)} out={len(result)}"
        f" | dropped_empty={skipped_empty} dropped_dup={skipped_dup}"
    )
    return result
