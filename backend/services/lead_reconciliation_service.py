"""
lead_reconciliation_service.py

Deterministic field-level reconciliation using per-field trust ordering.

Called after enrich_with_business_details() and before stamp_field_provenance()
so that *_candidate fields left by _apply_details are resolved before provenance
stamps are applied.

Trust ordering (highest → lowest):
  email:   hunter > json_ld > osm > scraped_html > scraped_contact_page > csv > fabricated
  phone:   json_ld > osm > scraped_html > scraped_contact_page
  domain:  osm > csv
  address: json_ld > osm > scraped_html > scraped_contact_page

Canonical normalization is applied before trust comparison so that formatting
differences alone do not trigger a reconciliation decision.
"""
import re

# ── Trust ordering ────────────────────────────────────────────────────────────

FIELD_TRUST_ORDER: dict[str, list[str]] = {
    "email":   ["hunter", "json_ld", "osm", "scraped_html", "scraped_contact_page", "csv", "fabricated"],
    "phone":   ["json_ld", "osm", "scraped_html", "scraped_contact_page"],
    "domain":  ["osm", "csv"],
    "address": ["json_ld", "osm", "scraped_html", "scraped_contact_page"],
    "contact": ["json_ld", "about_page", "scraped_html"],
}

_SENTINEL = len(FIELD_TRUST_ORDER["email"]) + 1  # rank for unknown sources


def trust_rank(field: str, source: str) -> int:
    """Return the trust rank index for a source string (lower = higher trust)."""
    order = FIELD_TRUST_ORDER.get(field, [])
    try:
        return order.index(source)
    except ValueError:
        return _SENTINEL


def pick_winner(field: str, current_val: str, current_src: str, candidate_val: str, candidate_src: str) -> tuple[str, str]:
    """
    Compare current and candidate values by trust rank.

    Returns (winning_value, winning_source).
    Ties keep current (stability over churn).
    """
    if trust_rank(field, candidate_src) < trust_rank(field, current_src):
        return candidate_val, candidate_src
    return current_val, current_src


# ── Canonical normalization ───────────────────────────────────────────────────

def canonical_phone(val: str) -> str:
    """Reduce to digits only; strip leading US country code (1) when 11 digits."""
    digits = re.sub(r"\D", "", val or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def canonical_email(val: str) -> str:
    """Lowercase and strip whitespace."""
    return (val or "").strip().lower()


# Subdomains that carry no business meaning and should be stripped from dedup keys.
# Subdomains NOT listed here (shop, schedule, careers, api, …) are preserved.
_STRIP_SUBDOMAINS = frozenset({"www", "m", "mobile"})


def canonical_domain(val: str) -> str:
    """Lowercase, strip whitespace, remove non-business leading subdomains.

    Stripped (first label only, one pass):  www  m  mobile
    Preserved (examples):  shop  schedule  careers  api  — and any other label
                           not in _STRIP_SUBDOMAINS.

    Requires at least three labels (subdomain.domain.tld) so bare domains
    like acme.com and two-label TLDs like co.uk are never touched.
    """
    d = (val or "").strip().lower()
    if not d:
        return d
    parts = d.split(".")
    if len(parts) > 2 and parts[0] in _STRIP_SUBDOMAINS:
        d = ".".join(parts[1:])
    return d


_COMPANY_SUFFIX_RE = re.compile(
    r"[,\s]+(llc|inc|ltd|corp)\.?$",
    re.IGNORECASE,
)


def canonical_company(val: str) -> str:
    """
    Normalize company name for aggregation dedup.

    Steps (applied in order):
      1. Strip leading/trailing whitespace
      2. Normalize curly apostrophes to straight apostrophe
      3. Strip one trailing legal suffix: LLC, Inc, Ltd, Corp
         (with optional preceding comma/space and optional trailing period)
      4. Strip any trailing comma or period left after suffix removal
      5. Collapse internal repeated whitespace to a single space
      6. Lowercase

    Only trailing suffixes are removed so "Corp Solutions" is unchanged.
    One suffix pass only — "Acme Corp, LLC" → "Acme Corp" (inner suffix kept).
    """
    s = (val or "").strip()
    s = s.replace("’", "'").replace("‘", "'")  # curly → straight apostrophe
    s = _COMPANY_SUFFIX_RE.sub("", s).strip()
    s = s.rstrip(".,").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


_CANONICALIZERS: dict[str, callable] = {
    "phone":   canonical_phone,
    "email":   canonical_email,
    "domain":  canonical_domain,
    "company": canonical_company,
}


def canonical_for(field: str, val: str) -> str:
    """Return the canonical form of val for the given field.

    Falls back to strip().lower() for fields without a dedicated normalizer
    (e.g. address), which eliminates trivial whitespace/case differences.
    """
    fn = _CANONICALIZERS.get(field)
    return fn(val) if fn else (val or "").strip().lower()


# ── Identity scoring ──────────────────────────────────────────────────────────

SIGNAL_WEIGHTS: dict[str, int] = {
    "domain":   3,
    "email":    3,
    "company":  2,
    "phone":    2,
    "address":  1,
}

_HIGH_CONF_THRESHOLD   = 4  # domain+company(5), phone+company(4), domain+phone(5), …
_MEDIUM_CONF_THRESHOLD = 2  # company alone(2), phone alone(2), domain alone(3), …


def compute_identity_confidence(
    lead_a: dict,
    lead_b: dict,
) -> tuple[str, list[str]]:
    """
    Compare two leads across five canonical signal fields.

    Returns (identity_confidence, identity_signals) where:
      identity_confidence : "high" | "medium" | "low" | "none"
      identity_signals    : field names whose canonical forms matched

    Signal weights:
      domain / email  → 3 pts  (strongest unique business identifiers)
      company / phone → 2 pts
      address         → 1 pt

    Confidence thresholds:
      score >= 4  → "high"    e.g. domain+company=5, phone+company=4
      score >= 2  → "medium"  e.g. domain alone=3, company alone=2
      score == 1  → "low"     address alone
      score == 0  → "none"

    A signal is counted only when BOTH leads carry a non-empty value for
    that field — a match against an empty string is not evidence of identity.
    """
    signals: list[str] = []
    score = 0

    for field, weight in SIGNAL_WEIGHTS.items():
        val_a = canonical_for(field, lead_a.get(field) or "")
        val_b = canonical_for(field, lead_b.get(field) or "")
        if val_a and val_b and val_a == val_b:
            signals.append(field)
            score += weight

    if score >= _HIGH_CONF_THRESHOLD:
        confidence = "high"
    elif score >= _MEDIUM_CONF_THRESHOLD:
        confidence = "medium"
    elif score > 0:
        confidence = "low"
    else:
        confidence = "none"

    return confidence, signals


def lead_richness_score(lead: dict) -> int:
    """
    Compute a deterministic data-completeness score for a single lead.
    Used to select which representative to retain when canonical keys collide.

    Scoring:
      verified email  (present AND not fabricated) : 2 pts
      verified domain (present AND domain_verified) : 2 pts
      phone present                                : 1 pt
      address present                              : 1 pt
    Maximum: 6

    Ties are broken by first-seen (existing representative kept) for stability.
    """
    score = 0
    if lead.get("email") and not lead.get("fabricated_email"):
        score += 2
    if lead.get("domain") and lead.get("domain_verified"):
        score += 2
    if lead.get("phone"):
        score += 1
    if lead.get("address"):
        score += 1
    return score


# ── Reconciliation ────────────────────────────────────────────────────────────

def reconcile_enriched_leads(leads: list[dict]) -> list[dict]:
    """
    Resolve *_candidate fields introduced by _apply_details when a field was
    already populated by a higher-priority source.

    For each field:
      1. Canonicalize both the current value and the candidate.
      2. If canonical forms match → skip (formatting difference only; log canonical_match).
      3. If canonical forms differ → run pick_winner using trust rankings.
      4. If candidate wins → swap the raw candidate value in (preserve original formatting).

    Currently reconciles: phone, address.
    Email and domain candidates are not yet introduced by the enrichment layer.

    Diagnostics:
      [RECONCILE] field=phone  canonical_match=True  lead=?  → skipped
      [RECONCILE] field=phone  kept=<src>  discarded=<src>  lead=?
    Summary:
      [RECONCILE] total=N  canonical_skipped=N  phone_swapped=N  address_swapped=N
    """
    canonical_skipped = phone_swapped = address_swapped = 0

    for lead in leads:
        company = lead.get("company") or lead.get("full_name") or "?"

        # ── phone ─────────────────────────────────────────────────────────────
        candidate_phone = lead.pop("phone_candidate", None)
        candidate_src   = lead.pop("phone_candidate_source", None)
        if candidate_phone and lead.get("phone") and candidate_src:
            if canonical_for("phone", lead["phone"]) == canonical_for("phone", candidate_phone):
                print(f"[RECONCILE] field=phone canonical_match=True lead={company!r} → skipped")
                canonical_skipped += 1
            else:
                current_src = lead.get("phone_source", "unknown")
                winner_val, winner_src = pick_winner(
                    "phone",
                    lead["phone"],   current_src,
                    candidate_phone, candidate_src,
                )
                if winner_val != lead["phone"]:
                    print(
                        f"[RECONCILE] field=phone"
                        f" kept={candidate_src!r} discarded={current_src!r}"
                        f" lead={company!r}"
                    )
                    lead["phone"]        = winner_val
                    lead["phone_source"] = winner_src
                    phone_swapped += 1
                else:
                    print(
                        f"[RECONCILE] field=phone"
                        f" kept={current_src!r} discarded={candidate_src!r}"
                        f" lead={company!r}"
                    )

        # ── address ───────────────────────────────────────────────────────────
        candidate_addr = lead.pop("address_candidate", None)
        candidate_asrc = lead.pop("address_candidate_source", None)
        if candidate_addr and lead.get("address") and candidate_asrc:
            if canonical_for("address", lead["address"]) == canonical_for("address", candidate_addr):
                print(f"[RECONCILE] field=address canonical_match=True lead={company!r} → skipped")
                canonical_skipped += 1
            else:
                current_asrc = lead.get("address_source", "unknown")
                winner_val, winner_src = pick_winner(
                    "address",
                    lead["address"],  current_asrc,
                    candidate_addr,   candidate_asrc,
                )
                if winner_val != lead["address"]:
                    print(
                        f"[RECONCILE] field=address"
                        f" kept={candidate_asrc!r} discarded={current_asrc!r}"
                        f" lead={company!r}"
                    )
                    lead["address"]        = winner_val
                    lead["address_source"] = winner_src
                    address_swapped += 1
                else:
                    print(
                        f"[RECONCILE] field=address"
                        f" kept={current_asrc!r} discarded={candidate_asrc!r}"
                        f" lead={company!r}"
                    )

    print(
        f"[RECONCILE] total={len(leads)}"
        f" canonical_skipped={canonical_skipped}"
        f" phone_swapped={phone_swapped}"
        f" address_swapped={address_swapped}"
    )
    return leads
