"""
lead_discovery_service.py

Lead discovery via Google Places Text Search API.
Falls back to an empty list on any error so the pipeline never crashes.
"""
import logging
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import requests

logger = logging.getLogger(__name__)

_PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def normalize_query(query: str) -> str:
    q = query.lower()
    for w in ["find", "show me", "looking for", "companies", "businesses", "near me"]:
        q = q.replace(w, "")
    return q.strip()


def extract_intent(query: str) -> str:
    KEYWORDS = [
        "restaurant", "plumber", "lawyer", "agency",
        "clinic", "dentist", "gym", "salon"
    ]
    q = query.lower()
    for k in KEYWORDS:
        if k in q:
            return k
    return query


def parse_query(query: str) -> str:
    q = query.lower()
    KEYWORDS = ["restaurant", "plumber", "lawyer", "agency", "clinic"]
    intent = None
    for k in KEYWORDS:
        if k in q:
            intent = k
            break
    if not intent:
        intent = q.split()[0] if q.split() else q
    return intent


def parse_natural_query(query: str) -> str:
    q = query.lower()

    # remove filler phrases
    fillers = [
        "find", "show me", "looking for", "i need",
        "companies", "businesses", "near me",
        "who are", "best", "top", "good"
    ]
    for f in fillers:
        q = q.replace(f, "")

    q = q.strip()

    # simple intent extraction
    KEYWORDS = [
        "restaurant", "plumber", "lawyer", "agency",
        "clinic", "dentist", "gym", "salon",
        "software company", "marketing agency"
    ]

    for k in KEYWORDS:
        if k in q:
            return k

    # fallback: first meaningful word
    return q.split()[0] if q else query


def fetch_leads_from_api(query: str, location: str) -> list[dict]:
    """
    Discover leads using the Google Places Text Search API.

    Args:
        query:    Search term (e.g. "marketing manager").
        location: Location filter (e.g. "San Francisco").

    Returns:
        A list of lead dicts with keys:
        full_name, company, title, location, website.
        Returns [] if the API key is missing, the request fails,
        or the response contains no results.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        logger.warning("GOOGLE_PLACES_API_KEY is not set — returning empty results")
        return []

    intent = parse_natural_query(query)
    print(f"[NLP] raw='{query}' → intent='{intent}'")

    params = {
        "query": f"{intent} in {location}",
        "key":   api_key,
    }

    try:
        response = requests.get(_PLACES_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.error("Google Places API request failed: %s", exc)
        return []

    print("[GOOGLE RAW RESPONSE]:", data)

    status = data.get("status")
    if status != "OK":
        logger.error("Google API returned status: %s — full response: %s", status, data)
        return []

    leads = []
    for result in data.get("results", []):
        leads.append({
            "full_name": result.get("name", ""),
            "company":   result.get("name", ""),
            "title":     query,
            "location":  result.get("formatted_address", ""),
            "website":   result.get("website", ""),
            "email":     None,
            "source":    "google",
        })

    for lead in leads:
        website = lead.get("website", "")
        if website:
            domain = urlparse(website).netloc.replace("www.", "")
        else:
            domain = ""
        lead["domain"] = domain

    print("[PARSED LEADS]:", leads[:2])
    logger.info("Google Places returned %d results for query=%r location=%r",
                len(leads), query, location)
    return leads
