# Trust hierarchy for enriched field sources (descending confidence).
_SOURCE_CONFIDENCE: dict[str, float] = {
    "osm":                  1.0,  # ground-truth from OpenStreetMap
    "json_ld":              0.9,  # schema.org structured data
    "scraped_contact_page": 0.7,  # tel:/regex on /contact page
    "scraped_html":         0.5,  # tel:/regex on homepage
    "scraped":              0.4,  # legacy generic label
}

_ENRICHED_FIELDS = ("phone", "address", "contact_name")


def _source_confidence(source: str | None) -> float | None:
    """Map an enrichment source tag to a [0.0, 1.0] confidence score.

    Returns None when source is absent (field was not enriched).
    Returns 0.3 for unrecognised source tags so future sources degrade
    gracefully rather than being treated as absent.
    """
    if not source:
        return None
    return _SOURCE_CONFIDENCE.get(source, 0.3)


def score_leads(leads: list[dict]) -> list[dict]:
    """
    Simple scoring + explainability
    """

    for lead in leads:
        score = 0
        reasons = []

        if lead.get("email"):
            if lead.get("fabricated_email"):
                score += 1
                reasons.append("estimated email")
            else:
                score += 2
                reasons.append("has email")

        if lead.get("domain"):
            score += 1
            reasons.append("has domain")

        if lead.get("website"):
            score += 1
            reasons.append("has website")

        if lead.get("domain_verified"):
            score += 1
            reasons.append("domain verified")

        if lead.get("mx_present"):
            score += 1
            reasons.append("MX present")

        lead["score"] = score
        # Fabricated emails cannot achieve "high" confidence — only a real,
        # verified email address qualifies a lead for that tier.
        if lead.get("fabricated_email") and score >= 3:
            lead["confidence"] = "medium"
        else:
            lead["confidence"] = (
                "high"   if score >= 3 else
                "medium" if score == 2 else
                "low"
            )
        lead["reason"] = ", ".join(reasons)

        # REMOVE old fields if present
        if "score_explanation" in lead:
            del lead["score_explanation"]

        # ── Enrichment-quality confidence scores ─────────────────────────────
        # Each enriched field gets a float in [0.0, 1.0] derived from its
        # *_source tag.  Fields that were never enriched get no key at all.
        for field in _ENRICHED_FIELDS:
            conf = _source_confidence(lead.get(f"{field}_source"))
            if conf is not None:
                lead[f"{field}_confidence"] = conf

    total         = len(leads)
    with_email    = sum(1 for l in leads if l.get("email"))
    real_email    = sum(1 for l in leads if l.get("email") and not l.get("fabricated_email"))
    fab_email     = sum(1 for l in leads if l.get("fabricated_email"))
    with_domain   = sum(1 for l in leads if l.get("domain"))
    with_website  = sum(1 for l in leads if l.get("website"))
    zero_signal   = sum(1 for l in leads if l.get("score", 0) == 0)
    phone_conf    = sum(1 for l in leads if l.get("phone_confidence") is not None)
    addr_conf     = sum(1 for l in leads if l.get("address_confidence") is not None)
    name_conf     = sum(1 for l in leads if l.get("contact_name_confidence") is not None)
    dom_verified  = sum(1 for l in leads if l.get("domain_verified"))
    mx_positive   = sum(1 for l in leads if l.get("mx_present"))
    dom_invalid   = sum(1 for l in leads if l.get("domain_verified") is False)
    print(
        f"[SCORER] total={total}"
        f" | email={with_email}/{total} (real={real_email} +2pts, fabricated={fab_email} +1pt)"
        f" | domain={with_domain}/{total} (+1pt)"
        f" | website={with_website}/{total} (+1pt)"
        f" | domain_verified={dom_verified}/{total} (+1pt)"
        f" | mx_present={mx_positive}/{total} (+1pt)"
        f" | domain_invalid={dom_invalid}/{total}"
        f" | zero_signal={zero_signal}/{total}"
        f" | phone_conf={phone_conf}/{total}"
        f" | addr_conf={addr_conf}/{total}"
        f" | name_conf={name_conf}/{total}"
    )

    return sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
