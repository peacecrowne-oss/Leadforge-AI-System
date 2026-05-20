"""
lead_enrichment_service.py

Simulated enrichment layer.
Fills in missing fields (currently: email) without calling external APIs.
Does NOT mutate the input list.
"""
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

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


def _apply_verification(v: dict, lead: dict) -> None:
    """Copy verification signals from v into lead, skipping None values."""
    for key in ("domain_verified", "mx_present", "phone_verified", "verification_checked_at"):
        val = v.get(key)
        if val is not None:
            lead[key] = val


_CONTACT_CONFIDENCE: dict[str, str] = {
    "json_ld":    "high",
    "about_page": "medium",
}


def _contact_confidence(source: str) -> str:
    return _CONTACT_CONFIDENCE.get(source, "low")


def _apply_details(details: dict, lead: dict) -> None:
    """Copy non-null enrichment fields from details into lead, preserving existing values.

    If details carries an 'enriched_at' timestamp (ISO-8601 UTC), each field
    that is written also receives a corresponding *_last_verified_at stamp.
    """
    ts = details.get("enriched_at")
    if details.get("phone"):
        if not lead.get("phone"):
            lead["phone"]        = details["phone"]
            lead["phone_source"] = details.get("phone_source", "scraped")
            if ts:
                lead["phone_last_verified_at"] = ts
        else:
            lead["phone_candidate"]        = details["phone"]
            lead["phone_candidate_source"] = details.get("phone_source", "scraped")
    if details.get("address"):
        if not lead.get("address"):
            lead["address"]        = details["address"]
            lead["address_source"] = details.get("address_source", "scraped")
            if ts:
                lead["address_last_verified_at"] = ts
        else:
            lead["address_candidate"]        = details["address"]
            lead["address_candidate_source"] = details.get("address_source", "scraped")
    if details.get("contact_name") and not lead.get("contact_name"):
        lead["contact_name"]       = details["contact_name"]
        lead["contact_role"]       = details.get("contact_role")
        lead["contact_source"]     = (
            details.get("contact_source")
            or details.get("contact_name_source")
            or "scraped"
        )
        lead["contact_confidence"] = _contact_confidence(lead["contact_source"])
        lead["_contact_candidates"] = details.get("_contact_candidates", 1)
        if ts:
            lead["contact_name_last_verified_at"] = ts


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
        import time as _time
        domain = updated["domain"]
        _t0 = _time.monotonic()

        def _ms() -> int:
            return round((_time.monotonic() - _t0) * 1000)

        try:
            cached = db_get_domain_cache(domain, max_age_days=_CACHE_TTL_DAYS)
        except Exception as exc:
            # KeyError if migration 015 columns are absent on a warm-cache row.
            # Treat as a cache miss so the lead still gets processed.
            print(f"[FETCH] domain={domain} cache_read=ERR elapsed_ms={_ms()} exc={exc!r}")
            cached = None
        if cached is not None:
            _apply_details(cached, updated)
            _apply_verification(cached, updated)
            print(f"[FETCH] domain={domain} cache=HIT elapsed_ms={_ms()}")
            return i, updated, True

        # ── Scrape business details ───────────────────────────────────────
        details: dict = {}
        try:
            from services.website_email_extractor import extract_business_details
            details = extract_business_details(domain)
            print(f"[FETCH] domain={domain} scrape=OK phone={bool(details.get('phone'))} elapsed_ms={_ms()}")
        except (OSError, ValueError, requests.exceptions.RequestException) as exc:
            print(f"[FETCH] domain={domain} scrape=ERR elapsed_ms={_ms()} exc={exc!r}")

        # ── Domain/MX/phone verification ─────────────────────────────────
        v: dict = {}
        try:
            from services.domain_verification_service import verify_domain_signals
            # Use the scraped phone (if found) for plausibility check;
            # fall back to a phone already on the lead (OSM-sourced, etc.).
            pending_phone = details.get("phone") or updated.get("phone")
            v = verify_domain_signals(domain, pending_phone)
        except (OSError, ValueError) as exc:
            print(f"[FETCH] domain={domain} verify=ERR elapsed_ms={_ms()} exc={exc!r}")

        # Cache enrichment + verification together (enriched_at is transient).
        try:
            db_set_domain_cache(domain, {**details, **v})
        except Exception as exc:
            print(f"[FETCH] domain={domain} cache_write=ERR elapsed_ms={_ms()} exc={exc!r}")

        # Stamp scrape time and apply to lead.
        details["enriched_at"] = datetime.now(timezone.utc).isoformat()
        _apply_details(details, updated)
        _apply_verification(v, updated)
        print(
            f"[FETCH] domain={domain} cache=MISS"
            f" verified={updated.get('domain_verified')} mx={updated.get('mx_present')}"
            f" elapsed_ms={_ms()}"
        )
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

    total      = len(enriched)
    with_ph    = sum(1 for l in enriched if l.get("phone"))
    with_addr  = sum(1 for l in enriched if l.get("address"))
    with_name  = sum(1 for l in enriched if l.get("contact_name"))
    verified   = sum(1 for l in enriched if l.get("domain_verified"))
    mx_pos     = sum(1 for l in enriched if l.get("mx_present"))
    dom_invalid = sum(1 for l in enriched if l.get("domain_verified") is False)
    print(
        f"[ENRICH_DETAILS] total={total}"
        f" | phone={with_ph} | address={with_addr} | contact_name={with_name}"
        f" | domain_verified={verified} | mx_present={mx_pos} | domain_invalid={dom_invalid}"
        f" | cache_hits={cache_hits} | cache_misses={cache_misses}"
    )

    # Contact extraction diagnostics
    contact_extracted_count = with_name
    contact_source_dist: dict[str, int] = {}
    ambiguous_contact_count = 0
    for _l in enriched:
        if _l.get("contact_name"):
            src = _l.get("contact_source") or "unknown"
            contact_source_dist[src] = contact_source_dist.get(src, 0) + 1
        if (_l.get("_contact_candidates") or 0) > 1:
            ambiguous_contact_count += 1
    print(
        f"[ENRICH_CONTACT] contact_extracted_count={contact_extracted_count}"
        f" contact_source_distribution={contact_source_dist}"
        f" ambiguous_contact_count={ambiguous_contact_count}"
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
                lead["email_source"] = "hunter"

        except Exception:
            pass

        enriched.append(lead)

    return enriched


def stamp_field_provenance(leads: list[dict]) -> list[dict]:
    """
    Stamp *_provider fields from existing *_source signals and acquisition metadata.

    Called once after all enrichment passes complete so every *_source field
    carries its final value.  Mutates the input list in place.

    Mapping logic:
      phone_provider   ← phone_source   (osm | json_ld | scraped_html | scraped_contact_page)
      address_provider ← address_source (same set of values)
      email_provider   ← fabricated flag > email_source (hunter) > acquisition source (csv/osm)
      domain_provider  ← acquisition source field when domain is present
    """
    for lead in leads:
        if lead.get("phone") and lead.get("phone_source"):
            lead["phone_provider"] = lead["phone_source"]

        if lead.get("address") and lead.get("address_source"):
            lead["address_provider"] = lead["address_source"]

        if lead.get("email"):
            if lead.get("fabricated_email"):
                lead["email_provider"] = "fabricated"
            elif lead.get("email_source"):
                lead["email_provider"] = lead["email_source"]
            else:
                lead["email_provider"] = lead.get("source") or "unknown"

        if lead.get("domain"):
            lead["domain_provider"] = lead.get("source") or "unknown"

    return leads
