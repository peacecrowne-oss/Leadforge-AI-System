from services.website_email_extractor import extract_emails_from_domain


def build_leads_from_domains(domains: list[str], location: str = "") -> list[dict]:
    """
    Convert domains into lead objects with extracted emails
    """

    leads = []

    for domain in domains:
        emails = extract_emails_from_domain(domain)

        lead = {
            "full_name": domain,
            "company": domain,
            "title": "owner",
            "roles": ["owner"],
            "location": location,
            "website": f"https://{domain}",
            "domain": domain,
            "email": emails[0] if emails else "",
            "email_candidates": emails,
            "source": "generated",
        }

        leads.append(lead)

    return leads
