"""
lead_enrichment_service.py

Simulated enrichment layer.
Fills in missing fields (currently: email) without calling external APIs.
Does NOT mutate the input list.
"""
import os
import requests

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")


def enrich_leads(leads: list[dict]) -> list[dict]:
    """
    Enrich a list of normalized leads.

    Current enrichment:
      - email: if None, generate a fake address as
               "<first_name>@<company_slug>.com"
               where first_name is the first word of full_name (lowercased)
               and company_slug is the company name lowercased with spaces removed.

    Returns a new list of lead dicts; originals are not modified.
    """
    enriched = []
    for lead in leads:
        updated = dict(lead)  # shallow copy — do not mutate original

        if updated.get("email") is None:
            full_name = (updated.get("full_name") or "").strip()
            company   = (updated.get("company")   or "").strip()

            first_name    = full_name.split()[0].lower() if full_name else "unknown"
            company_slug  = company.lower().replace(" ", "")

            updated["email"] = f"{first_name}@{company_slug}.com"

        enriched.append(updated)
    return enriched


def enrich_with_hunter(leads: list[dict]) -> list[dict]:
    """
    Enrich leads with real emails from the Hunter.io domain-search API.

    Requires HUNTER_API_KEY in the environment. If the key is missing,
    the original list is returned unchanged.
    Each lead must carry a "domain" key (populated by lead_discovery_service).
    Leads without a domain are passed through as-is.
    Exceptions per lead are silently swallowed so one bad response
    never aborts the whole batch.
    """
    if not HUNTER_API_KEY:
        return leads

    enriched = []

    for lead in leads:
        domain = lead.get("domain")

        if not domain:
            enriched.append(lead)
            continue

        try:
            res = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain":  domain,
                    "api_key": HUNTER_API_KEY,
                    "limit":   1,
                },
                timeout=5,
            )
            data = res.json()

            emails = data.get("data", {}).get("emails", [])

            preferred_roles = ["owner", "founder", "ceo", "marketing", "manager"]

            selected_email = None

            for e in emails:
                role  = (e.get("position") or "").lower()
                email = e.get("value")

                if any(r in role for r in preferred_roles):
                    selected_email = email
                    break

            # fallback to first email if no role match
            if not selected_email and emails:
                selected_email = emails[0].get("value")

            if selected_email:
                lead["email"] = selected_email

        except Exception:
            pass

        enriched.append(lead)

    return enriched
