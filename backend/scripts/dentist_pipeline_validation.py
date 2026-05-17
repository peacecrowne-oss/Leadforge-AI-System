"""
dentist_pipeline_validation.py

ANALYSIS ONLY — dry-run of the production pipeline without persisting to the database.

Runs dentist leads through every processing stage:
  discover → aggregate → normalize → deduplicate → enrich → score

Does NOT call store_leads, index_leads, db_save_job, or any background task.
Does NOT read from or write to SQLite, Typesense, or the in-memory JOBS/RESULTS cache.

Usage (run from the backend/ directory):
    python scripts/dentist_pipeline_validation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.osm_lead_source          import fetch_osm_leads          # noqa: E402
from services.csv_lead_source          import load_leads_from_csv       # noqa: E402
from services.lead_aggregation_service import aggregate_leads           # noqa: E402
from services.lead_processing_service  import normalize_leads, deduplicate_leads  # noqa: E402
from services.lead_enrichment_service  import enrich_leads              # noqa: E402
from services.lead_scoring_service     import score_leads               # noqa: E402

# ── Configuration ─────────────────────────────────────────────────────────────

QUERY    = "dentist"
LOCATION = "Houston, TX"
SAMPLE   = 8   # sample leads to display in the output section

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(num: int, denom: int) -> str:
    return f"{num / denom * 100:.0f}%" if denom else "n/a"


def _bar(value: float, width: int = 20) -> str:
    filled = min(width, round(value / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _trunc(s: str | None, n: int) -> str:
    s = (s or "—")
    return s[:n] + "…" if len(s) > n else s


# ── Validation runner ─────────────────────────────────────────────────────────

def run_validation() -> None:
    sep  = "=" * 70
    thin = "-" * 70

    print(sep)
    print("  DENTIST PIPELINE VALIDATION  (dry run — no data persisted)")
    print(f"  Query    : '{QUERY}'")
    print(f"  Location : {LOCATION}")
    print(f"  Note     : store_leads / index_leads / db_save_job are NOT called")
    print(sep)
    print()

    # ── Stage 1: Discover ────────────────────────────────────────────────────
    print("── STAGE 1: DISCOVER ──────────────────────────────────────────────")

    try:
        csv_leads = load_leads_from_csv("data/leads.csv")
    except Exception as exc:
        print(f"  CSV load failed: {exc}")
        csv_leads = []
    print(f"  CSV source : {len(csv_leads)} leads  (expected 0 — file is currently empty)")

    print(f"  OSM source : querying '{QUERY}' in {LOCATION} ...")
    try:
        osm_leads = fetch_osm_leads(QUERY, LOCATION)
    except Exception as exc:
        print(f"  OSM fetch failed: {exc}")
        osm_leads = []

    osm_total        = len(osm_leads)
    osm_with_website = sum(1 for l in osm_leads if l.get("website", "").strip())
    osm_with_domain  = sum(1 for l in osm_leads if l.get("domain",  "").strip())
    print(f"  OSM source : {osm_total} leads")
    print(f"    website tagged : {osm_with_website}/{osm_total} ({_pct(osm_with_website, osm_total)})")
    print(f"    domain tagged  : {osm_with_domain}/{osm_total}  ({_pct(osm_with_domain, osm_total)})")

    raw = aggregate_leads(csv_leads, osm_leads)
    print(f"  After aggregate : {len(raw)} leads")
    print()

    if not raw:
        print("  ⚠  No leads discovered. Verify Overpass API connectivity and bbox.")
        _end(sep)
        return

    # ── Stage 2: Normalize ───────────────────────────────────────────────────
    print("── STAGE 2: NORMALIZE ─────────────────────────────────────────────")
    normalized = normalize_leads(raw)
    print(f"  Input  : {len(raw)}")
    print(f"  Output : {len(normalized)}")
    print()

    # ── Stage 3: Deduplicate ─────────────────────────────────────────────────
    print("── STAGE 3: DEDUPLICATE ───────────────────────────────────────────")
    cleaned = deduplicate_leads(normalized)
    dropped = len(normalized) - len(cleaned)
    no_name_or_company = sum(
        1 for l in normalized
        if not (l.get("full_name") or "").strip()
        or not (l.get("company")   or "").strip()
    )
    print(f"  Input             : {len(normalized)}")
    print(f"  Missing name/co   : {no_name_or_company}  (these are dropped as invalid)")
    print(f"  Output            : {len(cleaned)}  ({dropped} dropped total)")
    print()

    if not cleaned:
        print("  ⚠  All leads dropped at deduplication.")
        _end(sep)
        return

    # ── Stage 4: Enrich ──────────────────────────────────────────────────────
    print("── STAGE 4: ENRICH ────────────────────────────────────────────────")
    enriched = enrich_leads(cleaned)

    # OSM leads enter with email="" (not None) so enrich_leads skips fabrication.
    # The check in enrich_leads is `if email is None`, not `if not email`.
    # This means: all emails here are real (from source data) or absent ("").
    real_email = sum(1 for l in enriched if l.get("email", "").strip())
    no_email   = sum(1 for l in enriched if not l.get("email", "").strip())
    print(f"  Real email present : {real_email}/{len(enriched)} ({_pct(real_email, len(enriched))})")
    print(f"  No email           : {no_email}/{len(enriched)}  ({_pct(no_email,    len(enriched))})")
    print(f"  Note: enrich_leads fabricates only when email is None.")
    print(f"        OSM leads have email='' so NO fabrication occurs here.")
    print()

    # ── Stage 5: Score ───────────────────────────────────────────────────────
    print("── STAGE 5: SCORE ─────────────────────────────────────────────────")
    scored = score_leads(enriched)
    print()

    high        = sum(1 for l in scored if l.get("confidence") == "high")
    medium      = sum(1 for l in scored if l.get("confidence") == "medium")
    low         = sum(1 for l in scored if l.get("confidence") == "low")
    zero_signal = sum(1 for l in scored if (l.get("score") or 0) == 0)

    total        = len(scored)
    with_website = sum(1 for l in scored if l.get("website", "").strip())
    with_domain  = sum(1 for l in scored if l.get("domain",  "").strip())
    with_email   = sum(1 for l in scored if l.get("email",   "").strip())

    # ── Pipeline funnel ───────────────────────────────────────────────────────
    print(sep)
    print("  PIPELINE FUNNEL")
    print(sep)
    stages = [
        ("Discovered (OSM)",  osm_total),
        ("After aggregate",   len(raw)),
        ("After normalize",   len(normalized)),
        ("After deduplicate", len(cleaned)),
        ("After enrich",      len(enriched)),
        ("After score",       total),
    ]
    top = stages[0][1] or 1
    for label, count in stages:
        pct_of_top = count / top * 100
        print(f"  {label:<22} : {count:>4}  {_bar(pct_of_top)}")
    print()

    # ── Quality summary ───────────────────────────────────────────────────────
    print(sep)
    print("  LEAD QUALITY SUMMARY")
    print(sep)
    print(f"  Total leads through pipeline : {total}")
    print()
    print(f"  Signal coverage:")
    print(f"    Website       : {with_website:>4} / {total}  ({_pct(with_website, total)})  {_bar(_pct_f(with_website, total))}")
    print(f"    Domain        : {with_domain:>4} / {total}  ({_pct(with_domain,  total)})  {_bar(_pct_f(with_domain,  total))}")
    print(f"    Email (real)  : {with_email:>4} / {total}  ({_pct(with_email,    total)})  {_bar(_pct_f(with_email,    total))}")
    print()
    print(f"  Confidence breakdown:")
    print(f"    high   : {high:>4}  ({_pct(high,   total)})  score ≥ 3  — email + domain/website present")
    print(f"    medium : {medium:>4}  ({_pct(medium, total)})  score == 2 — domain + website, no email")
    print(f"    low    : {low:>4}  ({_pct(low,    total)})  score ≤ 1  — website only, or zero signal")
    print(f"    zero   : {zero_signal:>4}  ({_pct(zero_signal, total)})  score == 0 — no contactable data at all")
    print()
    print(f"  Outreach-ready (immediate — real email present)  : {with_email}")
    print(f"  Outreach-ready (via website — best OSM proxy)    : {with_website}")
    print()

    # ── Sample leads ──────────────────────────────────────────────────────────
    print(sep)
    print(f"  SAMPLE LEADS  (top {min(SAMPLE, total)} by score)")
    print(sep)

    for i, lead in enumerate(scored[:SAMPLE], start=1):
        name       = _trunc(lead.get("full_name"), 38)
        email      = lead.get("email",   "") or "—"
        website    = _trunc(lead.get("website"),  45)
        domain     = _trunc(lead.get("domain"),   35)
        score      = lead.get("score",      0)
        confidence = lead.get("confidence", "—")
        reason     = lead.get("reason")    or "no signal"
        location   = _trunc(lead.get("location"), 35)

        print(f"  [{i:2d}] {name}")
        print(f"       score={score}  confidence={confidence}  signals=[{reason}]")
        print(f"       email  : {email}")
        print(f"       website: {website}")
        print(f"       domain : {domain}")
        print(f"       loc    : {location}")
        print()

    _end(sep)


def _pct_f(num: int, denom: int) -> float:
    return (num / denom * 100) if denom else 0.0


def _end(sep: str) -> None:
    print(sep)
    print("  END OF VALIDATION")
    print(sep)


if __name__ == "__main__":
    run_validation()
