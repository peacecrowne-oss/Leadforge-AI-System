from services.lead_reconciliation_service import (
    canonical_company,
    canonical_domain,
    canonical_email,
    canonical_phone,
    compute_identity_confidence,
    lead_richness_score,
)


def aggregate_leads(*lead_lists):
    """
    Merge multiple lead sources into one list with canonical deduplication.

    Dedup key: (canonical_company, canonical_domain_or_email)
      - canonical_company   : suffix-stripped, apostrophe-normalized, lowercased
      - canonical_domain    : non-business subdomains stripped (www, m, mobile)
      - email fallback      : canonical_email used as second key axis when domain absent

    Data structures:
      seen_canon   — canonical keys used for dedup
      seen_raw     — raw keys for canonical_agg_skips / domain / company diagnostics
      seen_leads   — current representative lead per canon_key (updated on upgrade)
      seen_indices — index of the representative in merged (enables O(1) replacement)
    """

    seen_canon:   set[tuple[str, str]]        = set()
    seen_raw:     set[tuple[str, str]]        = set()
    seen_leads:   dict[tuple[str, str], dict] = {}
    seen_indices: dict[tuple[str, str], int]  = {}
    merged: list[dict] = []

    discarded = 0
    canonical_agg_skips = 0
    duplicate_domain_collisions = 0
    canonical_company_collisions = 0
    apex_domain_collisions = 0

    identity_conf_dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
    strong_matches = 0
    weak_matches   = 0

    representative_upgrades = 0
    upgraded_keys: set[tuple[str, str]] = set()

    import time as _time
    _agg_t0 = _time.perf_counter()

    for leads in lead_lists:
        for lead in leads:
            raw_company = (lead.get("company") or "").lower()
            raw_domain  = (lead.get("domain")  or "").lower()
            raw_key     = (raw_company, raw_domain)

            canon_co         = canonical_company(lead.get("company") or "")
            canon_d          = canonical_domain(lead.get("domain") or "")
            # When domain is absent, use canonical email as secondary dedup axis.
            canon_domain_key = canon_d or canonical_email(lead.get("email") or "")
            canon_key        = (canon_co, canon_domain_key)

            company_was_normalized = (canon_co != raw_company)

            # m./mobile. stripping check (www. covered by duplicate_domain_collisions).
            raw_d_parts      = raw_domain.split(".")
            is_apex_stripped = (
                len(raw_d_parts) > 2 and raw_d_parts[0] in ("m", "mobile")
            )

            if canon_key in seen_canon:
                discarded += 1

                existing = seen_leads.get(canon_key)
                if existing is not None:
                    # Pairwise identity-confidence for this collision.
                    ic, _signals = compute_identity_confidence(existing, lead)
                    identity_conf_dist[ic] = identity_conf_dist.get(ic, 0) + 1
                    if ic == "high":
                        strong_matches += 1
                    elif ic in ("low", "none"):
                        weak_matches += 1

                    # Replace the representative if the incoming lead is richer.
                    existing_richness = lead_richness_score(existing)
                    incoming_richness = lead_richness_score(lead)
                    if incoming_richness > existing_richness:
                        idx = seen_indices[canon_key]
                        merged[idx]           = lead
                        seen_leads[canon_key] = lead
                        representative_upgrades += 1
                        upgraded_keys.add(canon_key)
                        print(
                            f"[AGGREGATE] representative_upgrade"
                            f" canon_key={canon_key}"
                            f" richness={existing_richness}→{incoming_richness}"
                            f" company={lead.get('company')!r}"
                        )

                if raw_key not in seen_raw:
                    canonical_agg_skips += 1
                    if canon_d != raw_domain:
                        duplicate_domain_collisions += 1
                    if company_was_normalized:
                        canonical_company_collisions += 1
                    if is_apex_stripped:
                        apex_domain_collisions += 1
                continue

            seen_canon.add(canon_key)
            seen_raw.add(raw_key)
            seen_indices[canon_key] = len(merged)   # record position before append
            seen_leads[canon_key]   = lead
            merged.append(lead)

    # ── Phone repeat diagnostics ──────────────────────────────────────────────
    _phone_counts: dict[str, int] = {}
    for _l in merged:
        _cp = canonical_phone(_l.get("phone") or "")
        if _cp:
            _phone_counts[_cp] = _phone_counts.get(_cp, 0) + 1

    _repeated_phones           = {p: c for p, c in _phone_counts.items() if c > 1}
    repeated_phone_count       = len(_repeated_phones)
    duplicate_phone_collisions = sum(c - 1 for c in _repeated_phones.values())
    _top_repeated_phones       = sorted(_repeated_phones.items(), key=lambda x: -x[1])[:5]
    if _top_repeated_phones:
        print(
            f"[AGGREGATE] repeated_phone_count={repeated_phone_count}"
            f" duplicate_phone_collisions={duplicate_phone_collisions}"
            f" top_repeated_phones={_top_repeated_phones}"
        )

    # ── Phone-based exact duplicate suppression ───────────────────────────────
    # Only suppresses when (canonical_company, canonical_domain, canonical_phone)
    # all match.  Different phone number → always kept (chain/franchise safe).
    _phone_triple_seen: dict[tuple[str, str, str], int] = {}
    _to_remove: set[int] = set()
    suppressed_exact_phone_dups = 0

    for _i, _l in enumerate(merged):
        _cp = canonical_phone(_l.get("phone") or "")
        if not _cp:
            continue
        _triple = (
            canonical_company(_l.get("company") or ""),
            canonical_domain(_l.get("domain") or ""),
            _cp,
        )
        if _triple in _phone_triple_seen:
            _existing_i = _phone_triple_seen[_triple]
            if lead_richness_score(_l) > lead_richness_score(merged[_existing_i]):
                _to_remove.add(_existing_i)
                _phone_triple_seen[_triple] = _i
            else:
                _to_remove.add(_i)
            suppressed_exact_phone_dups += 1
            print(
                f"[AGGREGATE] suppressed_exact_phone_dup"
                f" phone={_cp!r} company={_l.get('company')!r}"
                f" domain={(_l.get('domain') or '')!r}"
            )
        else:
            _phone_triple_seen[_triple] = _i

    if _to_remove:
        merged = [_l for _i, _l in enumerate(merged) if _i not in _to_remove]

    _agg_ms = round((_time.perf_counter() - _agg_t0) * 1000)
    richer_lead_replacements = len(upgraded_keys)
    total_input = sum(len(l) for l in lead_lists)
    print(
        f"[AGGREGATE] total_input={total_input} merged={len(merged)}"
        f" agg_ms={_agg_ms}"
        f" discarded_dups={discarded}"
        f" canonical_agg_skips={canonical_agg_skips}"
        f" duplicate_domain_collisions={duplicate_domain_collisions}"
        f" canonical_company_collisions={canonical_company_collisions}"
        f" apex_domain_collisions={apex_domain_collisions}"
        f" identity_conf={identity_conf_dist}"
        f" strong_matches={strong_matches}"
        f" weak_matches={weak_matches}"
        f" representative_upgrades={representative_upgrades}"
        f" richer_lead_replacements={richer_lead_replacements}"
        f" repeated_phone_count={repeated_phone_count}"
        f" duplicate_phone_collisions={duplicate_phone_collisions}"
        f" suppressed_exact_phone_dups={suppressed_exact_phone_dups}"
    )
    return merged
