"""
lead_pipeline_service.py

Full pipeline orchestration for lead discovery and processing.

Steps:
  1. Discover  – fetch raw leads from external API (simulated)
  2. Normalize – coerce into consistent schema
  3. Dedupe    – remove invalid and duplicate leads
  4. Enrich    – fill missing fields (e.g. email)
  5. Score     – attach AI/rule-based scores
  6. Store     – persist to database
  7. Index     – simulate Typesense indexing
"""
import uuid
from datetime import datetime, timezone

# from services.lead_discovery_service  import fetch_leads_from_api  # temporarily disabled for Bing scraper test
from services.csv_lead_source          import load_leads_from_csv
from services.osm_lead_source          import fetch_osm_leads
from services.lead_aggregation_service import aggregate_leads
from services.lead_processing_service import normalize_leads, deduplicate_leads
from services.lead_enrichment_service import enrich_leads, enrich_with_business_details, stamp_field_provenance
from services.lead_reconciliation_service import reconcile_enriched_leads
from services.lead_scoring_service    import score_leads
from services.lead_storage_service    import store_leads
from services.lead_indexing_service   import index_leads
from db.sqlite import db_save_job
from models import SearchJob, LeadSearchRequest


def run_pipeline(query: str, location: str, user_id: str, job_id: str | None = None) -> dict:
    """
    Run the full lead pipeline for the given search parameters.

    Args:
        query:    Keyword to match against title / company.
        location: Location filter string.
        user_id:  ID of the requesting user (used for DB storage).
        job_id:   Optional pre-created job id. If omitted, one is generated.

    Returns:
        Summary dict:
          {
            "job_id":     str,  # the job id used for storage
            "discovered": int,  # raw leads returned by the API
            "processed":  int,  # leads remaining after dedup/enrich/score
            "stored":     int,  # leads actually inserted into the DB
          }
    """
    import time as _time
    _t0 = _time.monotonic()

    def _ms() -> int:
        return round((_time.monotonic() - _t0) * 1000)

    if job_id is None:
        job_id = str(uuid.uuid4())

    print(f"[PIPELINE] START job_id={job_id} query={query!r} location={location!r}")

    # Step 1: Discover
    # raw = fetch_leads_from_api(query, location)  # temporarily disabled for Bing scraper test

    # Primary source: CSV
    source1 = load_leads_from_csv("data/leads.csv")
    print(f"[PIPELINE] csv_leads={len(source1)} elapsed_ms={_ms()}")

    # Secondary source: OpenStreetMap via Overpass API
    try:
        source2 = fetch_osm_leads(query, location)
        print(f"[PIPELINE] osm_leads={len(source2)} elapsed_ms={_ms()}")
    except Exception as exc:
        print(f"[PIPELINE] OSM fetch FAILED elapsed_ms={_ms()} exc={exc!r}")
        source2 = []

    raw = aggregate_leads(source1, source2)
    print(f"[PIPELINE] aggregate_count={len(raw)} elapsed_ms={_ms()}")
    if raw:
        _r = raw[0]
        print(
            f"[PIPELINE] sample_raw[0] full_name={_r.get('full_name')!r}"
            f" company={_r.get('company')!r}"
            f" domain={_r.get('domain')!r}"
            f" source={_r.get('source')!r}"
        )
    else:
        print("[PIPELINE] aggregate_count=0 → NO LEADS to process — check OSM/CSV sources")

    # Step 2: Normalize
    normalized = normalize_leads(raw)
    print(f"[PIPELINE] normalized_count={len(normalized)} elapsed_ms={_ms()}")
    if normalized:
        _n = normalized[0]
        print(
            f"[PIPELINE] sample_normalized[0] full_name={_n.get('full_name')!r}"
            f" company={_n.get('company')!r}"
            f" email={_n.get('email')!r}"
        )

    # Step 3: Deduplicate
    cleaned = deduplicate_leads(normalized)
    print(f"[PIPELINE] deduped_count={len(cleaned)} elapsed_ms={_ms()}")
    if not cleaned and normalized:
        print("[PIPELINE] WARNING: dedupe removed ALL leads — check full_name/company emptiness above")
    if cleaned:
        _c = cleaned[0]
        print(
            f"[PIPELINE] sample_cleaned[0] full_name={_c.get('full_name')!r}"
            f" company={_c.get('company')!r}"
            f" email={_c.get('email')!r}"
        )

    # Step 4: Enrich
    print(f"[PIPELINE] enrich_leads START elapsed_ms={_ms()}")
    enriched = enrich_leads(cleaned)
    print(f"[PIPELINE] enrich_leads DONE elapsed_ms={_ms()}")

    print(f"[PIPELINE] enrich_with_business_details START leads={len(enriched)} elapsed_ms={_ms()}")
    enriched = enrich_with_business_details(enriched)
    print(f"[PIPELINE] enrich_with_business_details DONE elapsed_ms={_ms()}")

    print(f"[PIPELINE] reconcile_enriched_leads START elapsed_ms={_ms()}")
    enriched = reconcile_enriched_leads(enriched)
    print(f"[PIPELINE] reconcile_enriched_leads DONE elapsed_ms={_ms()}")

    enriched = stamp_field_provenance(enriched)
    _fp: dict[str, dict[str, int]] = {"email": {}, "phone": {}, "domain": {}, "address": {}}
    for _l in enriched:
        for _fld in ("email", "phone", "domain", "address"):
            _v = _l.get(f"{_fld}_provider") or "unset"
            _fp[_fld][_v] = _fp[_fld].get(_v, 0) + 1
    print(f"[PIPELINE] field_provenance={_fp}")

    print(f"[PIPELINE] enriched_count={len(enriched)} elapsed_ms={_ms()}")

    # Step 5: Score
    print(f"[PIPELINE] score_leads START elapsed_ms={_ms()}")
    scored = score_leads(enriched)
    high   = sum(1 for l in scored if l.get("confidence") == "high")
    medium = sum(1 for l in scored if l.get("confidence") == "medium")
    low    = sum(1 for l in scored if l.get("confidence") == "low")
    print(f"[PIPELINE] scored_count={len(scored)} high={high} medium={medium} low={low} elapsed_ms={_ms()}")
    _prov: dict[str, int] = {}
    for _l in scored:
        _p = _l.get("provider") or "unknown"
        _prov[_p] = _prov.get(_p, 0) + 1
    print(f"[PIPELINE] provider_distribution={_prov}")

    # Step 6: Store
    print(f"[PIPELINE] store_leads START elapsed_ms={_ms()}")
    if scored:
        _pre = scored[0]
        print(
            f"[PIPELINE] sample_pre_store[0] full_name={_pre.get('full_name')!r}"
            f" company={_pre.get('company')!r}"
            f" id={_pre.get('id')!r}"
            f" score={_pre.get('score')}"
            f" confidence={_pre.get('confidence')!r}"
            f" email={_pre.get('email')!r}"
            f" fabricated={_pre.get('fabricated_email')}"
        )
    stored_count = store_leads(scored, user_id, job_id)
    print(f"[PIPELINE] stored_count(rowcount)={stored_count} elapsed_ms={_ms()}")
    # Verify actual DB count — cursor.rowcount is unreliable for executemany in Python <3.12
    from db.sqlite import db_connect as _db_connect
    with _db_connect() as _conn:
        _actual = _conn.execute(
            "SELECT COUNT(*) FROM job_leads WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
    print(f"[PIPELINE] actual_db_count={_actual} job_id={job_id} elapsed_ms={_ms()}")

    # Step 7: Index
    print(f"[PIPELINE] index_leads START elapsed_ms={_ms()}")
    index_leads(scored)
    print(f"[PIPELINE] index_leads DONE elapsed_ms={_ms()}")

    # Register job in jobs table so the UI can discover this batch.
    now = datetime.now(timezone.utc)
    print(f"[PIPELINE] db_save_job status=complete job_id={job_id} elapsed_ms={_ms()}")
    db_save_job(
        SearchJob(
            job_id=job_id,
            status="complete",
            created_at=now,
            updated_at=now,
            request=LeadSearchRequest(keywords=query, location=location),
            results_count=len(scored),
        ),
        user_id=user_id,
    )
    print(f"[PIPELINE] COMPLETE job_id={job_id} total_ms={_ms()}")

    return {
        "job_id":     job_id,
        "discovered": len(raw),
        "processed":  len(scored),
        "stored":     stored_count,
    }
