"""Deterministic rule-based lead scoring for LeadForge.

Computes a numeric score in [0.0, 1.0] and a per-factor breakdown (explanation)
for a given Lead against the originating LeadSearchRequest.

Design constraints:
- No randomness: same input always produces the same output.
- No external libraries or ML models.
- Transparent: each factor is independently inspectable.
- All factor weights sum to exactly 1.0.

Factor weights:
    seniority_match  0.30  — seniority tier inferred from job title
    title_match      0.25  — how well the title matches the search request
    keyword_match    0.20  — keyword tokens found in title / company / name
    location_match   0.15  — location matches requested location
    company_match    0.10  — company matches requested company
"""
from __future__ import annotations

from models import Lead, LeadSearchRequest

# ---------------------------------------------------------------------------
# Seniority tiers — checked in order; first match wins.
# Each entry: (list_of_substrings_to_check, tier_score).
# Substrings are matched case-insensitively inside the job title.
# ---------------------------------------------------------------------------
_SENIORITY_TIERS: list[tuple[list[str], float]] = [
    (["chief", "c-level", "cto", "ceo", "coo", "cfo"], 1.00),
    (["vp", "vice president"],                          0.90),
    (["director", "head of"],                           0.80),
    (["principal"],                                     0.75),
    (["staff engineer", "staff developer"],             0.70),
    (["senior", "sr."],                                 0.65),
    (["lead "],                                         0.60),
    (["manager"],                                       0.55),
    (["engineer", "developer", "scientist",
      "architect", "analyst", "consultant"],            0.45),
    (["associate"],                                     0.25),
    (["junior", "jr.", "intern", "trainee"],            0.10),
]

# Neutral seniority when title is absent or unrecognised.
_SENIORITY_DEFAULT = 0.35

_WEIGHTS: dict[str, float] = {
    "seniority_match": 0.30,
    "title_match":     0.25,
    "keyword_match":   0.20,
    "location_match":  0.15,
    "company_match":   0.10,
}

assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ---------------------------------------------------------------------------
# Factor helpers
# ---------------------------------------------------------------------------

def _contains_any(text: str, tokens: list[str]) -> bool:
    t = text.lower()
    return any(tok in t for tok in tokens)


def _seniority_score(title: str | None) -> float:
    """Return a seniority score based on the job title."""
    if not title:
        return _SENIORITY_DEFAULT
    for keywords, tier in _SENIORITY_TIERS:
        if _contains_any(title, keywords):
            return tier
    return _SENIORITY_DEFAULT


def _title_match_score(title: str | None, requested_title: str | None) -> float:
    """Return 1.0 on exact substring match, partial on token overlap, 0.5 if no filter."""
    if not requested_title:
        return 0.5  # no title filter → neutral
    if not title:
        return 0.0
    t = title.lower()
    req = requested_title.lower()
    if req in t:
        return 1.0
    tokens = [tok for tok in req.split() if tok]
    if not tokens:
        return 0.5
    matched = sum(1 for tok in tokens if tok in t)
    return round(matched / len(tokens), 4)


def _keyword_match_score(lead: Lead, keywords: str | None) -> float:
    """Return fraction of keyword tokens found in title + company + name (0.5 if no filter)."""
    if not keywords:
        return 0.5  # no keyword filter → neutral
    searchable = " ".join(
        part for part in [lead.title, lead.company, lead.full_name] if part
    ).lower()
    tokens = [tok for tok in keywords.lower().split() if tok]
    if not tokens:
        return 0.5
    matched = sum(1 for tok in tokens if tok in searchable)
    return round(matched / len(tokens), 4)


def _location_match_score(location: str | None, requested: str | None) -> float:
    """Return 1.0 if requested location is a substring of lead location, 0.5 if no filter."""
    if not requested:
        return 0.5
    if not location:
        return 0.0
    return 1.0 if requested.lower() in location.lower() else 0.0


def _company_match_score(company: str | None, requested: str | None) -> float:
    """Return 1.0 if requested company is a substring of lead company, 0.5 if no filter."""
    if not requested:
        return 0.5
    if not company:
        return 0.0
    return 1.0 if requested.lower() in company.lower() else 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_lead(
    lead: Lead,
    request: LeadSearchRequest,
) -> tuple[float, dict[str, float]]:
    """Compute a deterministic score and breakdown for a lead.

    Args:
        lead:    The candidate lead to score.
        request: The originating search request (provides filter context).

    Returns:
        (score, explanation) where:
          - score is a float clamped to [0.0, 1.0], rounded to 4 decimal places.
          - explanation maps each factor name to its weighted contribution.
    """
    raw: dict[str, float] = {
        "seniority_match": _seniority_score(lead.title),
        "title_match":     _title_match_score(lead.title, request.title),
        "keyword_match":   _keyword_match_score(lead, request.keywords),
        "location_match":  _location_match_score(lead.location, request.location),
        "company_match":   _company_match_score(lead.company, request.company),
    }

    explanation: dict[str, float] = {
        factor: round(raw[factor] * _WEIGHTS[factor], 4)
        for factor in _WEIGHTS
    }

    total = sum(explanation.values())
    score = round(max(0.0, min(1.0, total)), 4)
    return score, explanation
