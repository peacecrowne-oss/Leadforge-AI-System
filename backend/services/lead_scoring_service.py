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

    total        = len(leads)
    with_email   = sum(1 for l in leads if l.get("email"))
    real_email   = sum(1 for l in leads if l.get("email") and not l.get("fabricated_email"))
    fab_email    = sum(1 for l in leads if l.get("fabricated_email"))
    with_domain  = sum(1 for l in leads if l.get("domain"))
    with_website = sum(1 for l in leads if l.get("website"))
    zero_signal  = sum(1 for l in leads if l.get("score", 0) == 0)
    print(
        f"[SCORER] total={total}"
        f" | email={with_email}/{total} (real={real_email} +2pts, fabricated={fab_email} +1pt)"
        f" | domain={with_domain}/{total} (+1pt)"
        f" | website={with_website}/{total} (+1pt)"
        f" | zero_signal={zero_signal}/{total}"
    )

    return sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
