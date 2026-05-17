def aggregate_leads(*lead_lists):
    """
    Merge multiple lead sources into one list
    with deduplication
    """

    seen = set()
    merged = []

    for leads in lead_lists:
        for lead in leads:
            key = (
                lead.get("company", "").lower(),
                lead.get("domain", "").lower()
            )

            if key in seen:
                continue

            seen.add(key)
            merged.append(lead)

    return merged
