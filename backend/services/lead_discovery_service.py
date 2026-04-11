"""
lead_discovery_service.py

Lead discovery via Google Places Text Search API.
Falls back to an empty list on any error so the pipeline never crashes.
"""
import logging
import os

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import requests

logger = logging.getLogger(__name__)

_PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


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

    params = {
        "query": f"{query} in {location}",
        "key":   api_key,
    }

    try:
        response = requests.get(_PLACES_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.error("Google Places API request failed: %s", exc)
        return []

    leads = []
    for result in data.get("results", []):
        leads.append({
            "full_name": result.get("name", ""),
            "company":   result.get("name", ""),
            "title":     query,
            "location":  result.get("formatted_address", ""),
            "website":   result.get("website", ""),
        })

    logger.info("Google Places returned %d results for query=%r location=%r",
                len(leads), query, location)
    return leads
