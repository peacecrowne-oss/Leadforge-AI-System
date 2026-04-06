"""
lead_enrichment_service.py

Simulated enrichment layer.
Fills in missing fields (currently: email) without calling external APIs.
Does NOT mutate the input list.
"""


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
