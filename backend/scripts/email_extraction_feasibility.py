"""
email_extraction_feasibility.py

ANALYSIS ONLY — not wired to the production pipeline.

Measures how many OSM-discovered business websites expose real contact
email addresses in their homepage HTML using a lightweight regex scan.

Usage (run from the backend/ directory):
    python scripts/email_extraction_feasibility.py

No new dependencies required — uses only `requests` (already in the project)
and the standard library.  Does NOT import from or modify any service used
by the production pipeline.

What this script does NOT do:
  - It does not crawl contact pages (homepage only).
  - It does not write results to any file or database.
  - It does not modify leads.csv or any pipeline state.
  - It does not call enrich_leads or any enrichment service.
"""
import re
import sys
import time
from pathlib import Path

import requests

# Allow `from services.xxx import ...` when run from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.osm_lead_source import fetch_osm_leads  # noqa: E402


# ── Configuration ─────────────────────────────────────────────────────────────

SAMPLE_SIZE   = 20     # max websites to test
FETCH_TIMEOUT = 5      # per-request timeout in seconds
REQUEST_DELAY = 0.5    # polite delay between consecutive requests

# ── Email regex ───────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Patterns that reliably flag non-contact garbage found in HTML:
#   - system/automated accounts (noreply, postmaster, abuse)
#   - placeholder domains (example.com, test., localhost)
#   - schema.org / JSON-LD artefacts
#   - image path fragments misread as email prefixes
#   - common website-builder support addresses
NOISE_RE = re.compile(
    r"(noreply|no-reply|donotreply|do-not-reply|"
    r"@example\.|@test\.|@localhost|"
    r"sentry\.|schema\.org|"
    r"support@wix\.|postmaster@|abuse@|"
    r"\.png@|\.jpg@|\.gif@|\.svg@|\.webp@|"
    r"your@|name@|email@|user@|address@)",
    re.IGNORECASE,
)


# ── Core helpers ──────────────────────────────────────────────────────────────

def fetch_homepage(url: str) -> tuple[bool, str]:
    """GET the homepage.  Returns (reachable, html_text)."""
    if not url.startswith("http"):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; research-script/1.0)"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.8",
    }

    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=FETCH_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            return True, resp.text
        return False, ""
    except Exception:
        return False, ""


def extract_emails(html: str) -> list[str]:
    """Return deduplicated, noise-filtered emails found in raw HTML."""
    seen:   set[str]  = set()
    result: list[str] = []

    for email in EMAIL_RE.findall(html):
        lower = email.lower()
        if lower in seen:
            continue
        if NOISE_RE.search(lower):
            continue
        seen.add(lower)
        result.append(email)

    return result


# ── Analysis runner ───────────────────────────────────────────────────────────

def run_analysis() -> None:
    bar = "=" * 66

    print(bar)
    print("  EMAIL EXTRACTION FEASIBILITY TEST")
    print("  Source  : OSM Overpass API  (Houston, TX — restaurant bounding box)")
    print(f"  Cap     : {SAMPLE_SIZE} websites   timeout={FETCH_TIMEOUT}s   delay={REQUEST_DELAY}s")
    print(bar)
    print()

    # ── Step 1: Fetch OSM leads ───────────────────────────────────────────────
    print("Fetching OSM leads via Overpass API ...")
    try:
        all_leads = fetch_osm_leads("restaurant", "Houston, TX")
    except Exception as exc:
        print(f"  OSM fetch failed: {exc}")
        print("  Cannot run analysis without lead data.")
        return

    print(f"  Total leads returned  : {len(all_leads)}")

    with_site = [l for l in all_leads if l.get("website", "").strip()]
    print(f"  Leads with website tag: {len(with_site)}")

    if not with_site:
        print()
        print("  NO WEBSITES FOUND IN OSM DATA.")
        print("  The Overpass bounding box returns business nodes, but OSM")
        print("  contributors have not tagged most of these businesses with")
        print("  a 'website' key.  Homepage extraction cannot be tested from")
        print("  this source without first resolving business websites via")
        print("  an external lookup (e.g. Google Places, domain generation).")
        print()
        print("  RECOMMENDATION: Homepage extraction is blocked at the data-")
        print("  collection layer, not the extraction layer.  Fix the website-")
        print("  tag gap before wiring email extraction into the pipeline.")
        return

    sample = with_site[:SAMPLE_SIZE]

    print()
    print(f"Testing {len(sample)} website(s) ...")
    print("-" * 66)

    # ── Step 2: Test each website ─────────────────────────────────────────────
    rows: list[dict] = []

    for idx, lead in enumerate(sample, start=1):
        url    = lead.get("website", "").strip()
        domain = lead.get("domain", "")
        name   = (lead.get("company") or lead.get("full_name") or domain or url)[:40]

        print(f"[{idx:2d}/{len(sample)}] {name:<40} ", end="", flush=True)

        reachable, html = fetch_homepage(url)

        if not reachable:
            print("UNREACHABLE")
            rows.append({"name": name, "url": url, "domain": domain,
                         "reachable": False, "emails": []})
        else:
            emails = extract_emails(html)
            if emails:
                print(f"OK  {len(emails)} email(s) → {emails[0]}")
            else:
                print("OK  reachable, 0 emails found")
            rows.append({"name": name, "url": url, "domain": domain,
                         "reachable": True, "emails": emails})

        if idx < len(sample):
            time.sleep(REQUEST_DELAY)

    # ── Step 3: Summary report ────────────────────────────────────────────────
    print()
    print(bar)
    print("  RESULTS SUMMARY")
    print(bar)

    total       = len(rows)
    reachable_n = sum(1 for r in rows if r["reachable"])
    with_email  = sum(1 for r in rows if r["emails"])
    all_emails  = [e for r in rows for e in r["emails"]]

    print(f"  Websites tested              : {total}")
    print(f"  Websites reachable (HTTP 200): {reachable_n:2d} / {total}  ({_pct(reachable_n, total)}%)")
    print(f"  Reachable with visible email : {with_email:2d} / {reachable_n}  ({_pct(with_email, reachable_n)}%)")
    print(f"  Total email addresses found  : {len(all_emails)}")
    print()

    if with_email:
        print("  SAMPLE EMAILS FOUND:")
        for r in rows:
            if r["emails"]:
                for email in r["emails"][:2]:    # show up to 2 per domain
                    print(f"    {r['domain']:<34}  {email}")
        print()

    unreachable = [r for r in rows if not r["reachable"]]
    if unreachable:
        print(f"  UNREACHABLE SITES ({len(unreachable)}):")
        for r in unreachable:
            print(f"    {r['url']}")
        print()

    multi = [r for r in rows if len(r["emails"]) > 1]
    if multi:
        print(f"  SITES WITH MULTIPLE EMAILS ({len(multi)}):")
        for r in multi:
            print(f"    {r['domain']:<34}  {r['emails'][:3]}")
        print()

    if reachable_n > 0:
        rate = with_email / reachable_n * 100
        verdict = (
            "VIABLE — enough sites expose emails to justify wiring into the pipeline."
            if rate >= 30
            else "MARGINAL — some emails visible but yield may not justify per-request cost."
            if rate >= 15
            else "LOW YIELD — fewer than 15% of reachable sites expose a contact email."
        )
        print(f"  Extraction rate (of reachable): {rate:.0f}%")
        print(f"  VERDICT: {verdict}")
        print()

    print(bar)
    print("  END OF ANALYSIS")
    print(bar)


def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "n/a"
    return f"{num / denom * 100:.0f}"


if __name__ == "__main__":
    run_analysis()
