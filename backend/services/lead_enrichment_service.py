"""
lead_enrichment_service.py

Simulated enrichment layer.
Fills in missing fields (currently: email) without calling external APIs.
Does NOT mutate the input list.
"""
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.sqlite import db_get_domain_cache, db_set_domain_cache

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

        if not updated.get("email"):
            full_name = (updated.get("full_name") or "").strip()
            company   = (updated.get("company")   or "").strip()

            first_name   = full_name.split()[0].lower() if full_name else "unknown"
            company_slug = company.lower().replace(" ", "")

            updated["email"]            = f"{first_name}@{company_slug}.com"
            updated["fabricated_email"] = True

        enriched.append(updated)
    return enriched


_ENRICH_WORKERS = 6
_CACHE_TTL_DAYS = 7


def _apply_details(details: dict, lead: dict) -> None:
    """Copy non-null enrichment fields from details into lead, preserving existing values."""
    if details.get("phone") and not lead.get("phone"):
        lead["phone"]        = details["phone"]
        lead["phone_source"] = details.get("phone_source", "scraped")
    if details.get("address") and not lead.get("address"):
        lead["address"]        = details["address"]
        lead["address_source"] = details.get("address_source", "scraped")
    if details.get("contact_name") and not lead.get("contact_name"):
        lead["contact_name"]        = details["contact_name"]
        lead["contact_name_source"] = details.get("contact_name_source", "scraped")


def enrich_with_business_details(leads: list[dict]) -> list[dict]:
    """
    Web-scrape phone, address, and contact_name for leads that have a domain.

    Preserves any values already present (OSM-sourced or previously set).
    Per-lead exceptions are swallowed so one bad fetch never aborts the batch.
    Each written field is paired with a *_source key:
      "osm"                  — already set at discovery (highest trust)
      "json_ld"              — structured data from homepage
      "scraped_html"         — tel: link or regex on homepage
      "scraped_contact_page" — tel: link or regex on /contact
    """
    # Partition leads into those with a domain (need HTTP) and those without.
    indexed   = list(enumerate(leads))          # keep original order
    to_fetch  = [(i, dict(lead)) for i, lead in indexed if lead.get("domain")]
    no_domain = {i: dict(lead) for i, lead in indexed if not lead.get("domain")}

    results: dict[int, dict] = dict(no_domain)

    def _fetch_one(i: int, updated: dict) -> tuple[int, dict, bool]:
        """Returns (original_index, enriched_lead, cache_hit)."""
        domain = updated["domain"]

        cached = db_get_domain_cache(domain, max_age_days=_CACHE_TTL_DAYS)
        if cached is not None:
            _apply_details(cached, updated)
            return i, updated, True

        try:
            from services.website_email_extractor import extract_business_details
            details = extract_business_details(domain)
            db_set_domain_cache(domain, details)
            _apply_details(details, updated)
        except (OSError, ValueError, requests.exceptions.RequestException):
            pass
        return i, updated, False

    cache_hits = cache_misses = 0
    with ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, i, updated): i for i, updated in to_fetch}
        for future in as_completed(futures):
            i, updated, hit = future.result()
            results[i] = updated
            if hit:
                cache_hits += 1
            else:
                cache_misses += 1

    # Rebuild in original order.
    enriched = [results[i] for i in range(len(leads))]

    total     = len(enriched)
    with_ph   = sum(1 for l in enriched if l.get("phone"))
    with_addr = sum(1 for l in enriched if l.get("address"))
    with_name = sum(1 for l in enriched if l.get("contact_name"))
    print(
        f"[ENRICH_DETAILS] total={total}"
        f" | phone={with_ph} | address={with_addr} | contact_name={with_name}"
        f" | cache_hits={cache_hits} | cache_misses={cache_misses}"
    )
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
