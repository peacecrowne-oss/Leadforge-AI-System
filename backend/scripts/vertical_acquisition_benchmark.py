"""
vertical_acquisition_benchmark.py

ANALYSIS ONLY — not wired to the production pipeline.

Tests OSM lead acquisition quality across business verticals using the
namespace-aware discovery system (amenity=, shop=, craft=).

Measures for each category:
  - total leads returned from the Overpass bbox query
  - website coverage %  (leads with a non-empty website tag)
  - domain coverage %   (leads with a non-empty domain tag)
  - OSM namespace used  (amenity / shop / craft)

Usage (run from the backend/ directory):
    python scripts/vertical_acquisition_benchmark.py

No new dependencies — uses only `requests` (already in the project) and the
standard library.  Does NOT import from or modify any route, enrichment
service, pipeline, or database state.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.osm_lead_source import (  # noqa: E402
    AMENITY_MAP,
    _SHOP_OR_CRAFT_KEYWORDS,
    fetch_osm_leads,
)

# ── Configuration ─────────────────────────────────────────────────────────────

TEST_LOCATION = "Houston, TX"
REQUEST_DELAY = 1.5   # polite delay between Overpass requests (seconds)

TEST_CATEGORIES = [
    "restaurant",
    "dentist",
    "clinic",
    "salon",
    "barber",
    "plumber",
    "electrician",
    "mechanic",
    "bakery",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _namespace_for(keyword: str) -> str:
    """Return the OSM namespace that fetch_osm_leads will use for this keyword."""
    if keyword in _SHOP_OR_CRAFT_KEYWORDS:
        return _SHOP_OR_CRAFT_KEYWORDS[keyword].split("=", 1)[0]  # "craft" or "shop"
    if keyword in AMENITY_MAP:
        return "amenity"
    return "amenity"  # fallback


def _resolved_value(keyword: str) -> str:
    """Return the OSM tag value that will appear in the Overpass query."""
    if keyword in _SHOP_OR_CRAFT_KEYWORDS:
        return _SHOP_OR_CRAFT_KEYWORDS[keyword].split("=", 1)[1]
    if keyword in AMENITY_MAP:
        return AMENITY_MAP[keyword]
    return "restaurant"


def _pct(num: int, denom: int) -> str:
    return f"{num / denom * 100:.0f}%" if denom else "n/a"


def _bar(value: float, width: int = 24) -> str:
    filled = min(width, round(value / 100 * width))
    return "█" * filled + "░" * (width - filled)


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark() -> None:
    sep  = "=" * 72
    thin = "-" * 72

    print(sep)
    print("  OSM VERTICAL ACQUISITION BENCHMARK")
    print(f"  Location  : {TEST_LOCATION}")
    print(f"  Source    : Overpass API  (overpass.kumi.systems)")
    print(f"  Categories: {len(TEST_CATEGORIES)}")
    print(f"  Delay     : {REQUEST_DELAY}s between requests")
    print(sep)
    print()

    rows: list[dict] = []

    for idx, category in enumerate(TEST_CATEGORIES, start=1):
        ns  = _namespace_for(category)
        val = _resolved_value(category)
        print(f"[{idx:2d}/{len(TEST_CATEGORIES)}]  {category:<14}  query → {ns}={val}")

        try:
            leads = fetch_osm_leads(category, TEST_LOCATION)
        except Exception as exc:
            print(f"         ERROR: {exc}")
            rows.append({
                "category":     category,
                "namespace":    ns,
                "total":        0,
                "with_website": 0,
                "with_domain":  0,
                "error":        str(exc),
            })
            if idx < len(TEST_CATEGORIES):
                time.sleep(REQUEST_DELAY)
            continue

        total        = len(leads)
        with_website = sum(1 for l in leads if l.get("website", "").strip())
        with_domain  = sum(1 for l in leads if l.get("domain",  "").strip())

        rows.append({
            "category":     category,
            "namespace":    ns,
            "total":        total,
            "with_website": with_website,
            "with_domain":  with_domain,
            "error":        None,
        })

        if idx < len(TEST_CATEGORIES):
            time.sleep(REQUEST_DELAY)

    # ── Results table ─────────────────────────────────────────────────────────
    print()
    print(sep)
    print("  RESULTS TABLE")
    print(sep)
    hdr = (
        f"  {'Category':<14}  {'Namespace':<8}  "
        f"{'Leads':>6}  {'Website':>9}  {'Domain':>9}"
    )
    print(hdr)
    print(thin)

    for r in rows:
        if r["error"]:
            print(
                f"  {r['category']:<14}  {r['namespace']:<8}  "
                f"{'ERR':>6}  {'—':>9}  {'—':>9}"
            )
        else:
            print(
                f"  {r['category']:<14}"
                f"  {r['namespace']:<8}"
                f"  {r['total']:>6}"
                f"  {_pct(r['with_website'], r['total']):>9}"
                f"  {_pct(r['with_domain'],  r['total']):>9}"
            )

    print()

    # ── Analysis ──────────────────────────────────────────────────────────────
    valid = [r for r in rows if not r["error"] and r["total"] > 0]
    zero  = [r for r in rows if not r["error"] and r["total"] == 0]

    print(sep)
    print("  ANALYSIS")
    print(sep)

    if not valid:
        print()
        print("  No results — check Overpass API connectivity.")
        print()
        print(sep)
        print("  END OF BENCHMARK")
        print(sep)
        return

    # Ranked by lead volume
    by_leads = sorted(valid, key=lambda r: r["total"], reverse=True)
    print()
    print("  LEAD VOLUME  (total nodes returned per vertical)")
    print(thin)
    for r in by_leads:
        scale   = max(1, max(x["total"] for x in by_leads))
        bar_pct = r["total"] / scale * 100
        print(
            f"  {r['category']:<14}  {r['total']:>5} leads  "
            f"{_bar(bar_pct)}  [{r['namespace']}]"
        )

    # Ranked by website coverage
    by_web = sorted(
        valid,
        key=lambda r: r["with_website"] / r["total"],
        reverse=True,
    )
    print()
    print("  WEBSITE COVERAGE  (leads with a contactable website tag)")
    print(thin)
    for r in by_web:
        pct = r["with_website"] / r["total"] * 100
        print(
            f"  {r['category']:<14}  {pct:>5.0f}%  "
            f"{_bar(pct)}  ({r['with_website']}/{r['total']})"
        )

    # Outreach-readiness score = absolute count of leads with a website
    by_outreach = sorted(valid, key=lambda r: r["with_website"], reverse=True)
    print()
    print("  OUTREACH-READY LEADS  (volume × coverage — absolute website count)")
    print(thin)
    for r in by_outreach:
        print(
            f"  {r['category']:<14}  {r['with_website']:>5} contactable leads"
        )

    # Namespace breakdown
    by_ns: dict[str, list[dict]] = {}
    for r in valid:
        by_ns.setdefault(r["namespace"], []).append(r)
    print()
    print("  NAMESPACE BREAKDOWN")
    print(thin)
    for ns, group in sorted(by_ns.items()):
        names = ", ".join(x["category"] for x in group)
        print(f"  {ns:<8}  → {names}")

    # Sparse / zero coverage
    if zero:
        print()
        print("  SPARSE / ZERO-LEAD VERTICALS  (no OSM nodes found in bbox)")
        print(thin)
        for r in zero:
            print(f"  {r['category']:<14}  namespace={r['namespace']}  (0 nodes)")

    # Best for production
    if by_outreach:
        best = by_outreach[0]
        pct  = best["with_website"] / best["total"] * 100 if best["total"] else 0
        print()
        print("  RECOMMENDATION")
        print(thin)
        print(
            f"  Best for production outreach: '{best['category']}'"
            f"  ({best['with_website']} contactable leads, {pct:.0f}% website coverage)"
        )

    print()
    print(sep)
    print("  END OF BENCHMARK")
    print(sep)


if __name__ == "__main__":
    run_benchmark()
