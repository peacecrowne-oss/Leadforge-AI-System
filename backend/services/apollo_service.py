"""Apollo.io lead fetching service for LeadForge.

Calls the Apollo People Search API and normalizes the response into a
flat list of lead dicts ready for downstream processing (scoring, DB insert).

Design constraints:
- No FastAPI imports; no route definitions.
- No DB calls; caller is responsible for persistence.
- APOLLO_API_KEY is read from the environment; raises ValueError if absent.
- Returns plain dicts (not Pydantic models) so this module stays decoupled
  from models.py and can be tested independently.
"""
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error

_APOLLO_SEARCH_URL = "https://api.apollo.io/v1/mixed_people/search"


def fetch_apollo_leads(query: dict) -> list[dict]:
    """Fetch leads from Apollo People Search and return normalized records.

    Args:
        query: Search parameters. Recognised keys:
            - keywords  (str)  Free-text keywords
            - title     (str)  Target job title
            - location  (str)  City, state, or country
            - company   (str)  Target company name
            - limit     (int)  Max results to return (default 25, max 100)

    Returns:
        List of dicts, each containing:
            name, title, company, email, location

    Raises:
        ValueError:  APOLLO_API_KEY is not set in the environment.
        RuntimeError: Apollo returned a non-200 HTTP status.
    """
    api_key = os.getenv("APOLLO_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "APOLLO_API_KEY is not set. Add it to your .env file before calling Apollo."
        )

    limit = min(int(query.get("limit", 25)), 100)

    # Build the Apollo request payload.
    # person_titles and person_locations expect lists in the Apollo v1 API.
    payload: dict = {
        "api_key": api_key,
        "page": 1,
        "per_page": limit,
    }

    if query.get("keywords"):
        payload["q_keywords"] = query["keywords"]

    if query.get("title"):
        payload["person_titles"] = [query["title"]]

    if query.get("location"):
        payload["person_locations"] = [query["location"]]

    if query.get("company"):
        payload["organization_names"] = [query["company"]]

    raw_leads = _call_apollo(payload)
    return [_normalize(person) for person in raw_leads]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_apollo(payload: dict) -> list[dict]:
    """POST payload to Apollo and return the people list.

    Uses stdlib urllib so no extra dependency is required beyond httpx
    being available at the call site (see note below). In this MVP we use
    urllib directly to avoid adding a hard dependency; swap to httpx once
    it is added to requirements.txt.

    Raises:
        RuntimeError on non-200 response or network error.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _APOLLO_SEARCH_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Apollo API returned HTTP {exc.code}: {body_text}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Apollo API request failed: {exc.reason}") from exc

    return data.get("people", [])


def _normalize(person: dict) -> dict:
    """Map a single Apollo person record to our flat lead schema.

    Apollo field          → Our field
    ----------------------------------------
    first_name + last_name → name
    title                  → title
    organization.name      → company
    email                  → email
    city + state           → location  (comma-joined, blanks skipped)
    """
    first = (person.get("first_name") or "").strip()
    last = (person.get("last_name") or "").strip()
    name = " ".join(part for part in [first, last] if part) or None

    org = person.get("organization") or {}
    company = (org.get("name") or "").strip() or None

    location_parts = [
        (person.get("city") or "").strip(),
        (person.get("state") or "").strip(),
    ]
    location = ", ".join(part for part in location_parts if part) or None

    return {
        "name":     name,
        "title":    (person.get("title") or "").strip() or None,
        "company":  company,
        "email":    (person.get("email") or "").strip() or None,
        "location": location,
    }
