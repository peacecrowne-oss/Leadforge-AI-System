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
from services.lead_enrichment_service import enrich_leads, enrich_with_business_details
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
    if job_id is None:
        job_id = str(uuid.uuid4())

    # Step 1: Discover
    # raw = fetch_leads_from_api(query, location)  # temporarily disabled for Bing scraper test

    # Primary source: CSV
    source1 = load_leads_from_csv("data/leads.csv")
    print(f"[PIPELINE] csv_leads={len(source1)}")

    # Secondary source: OpenStreetMap via Overpass API
    try:
        source2 = fetch_osm_leads(query, location)
        print(f"[PIPELINE] osm_leads={len(source2)}")
    except Exception as exc:
        print(f"[PIPELINE] OSM fetch failed, falling back to empty source2: {exc}")
        source2 = []

    raw = aggregate_leads(source1, source2)
    print(f"[PIPELINE] aggregate_count={len(raw)}")

    # Step 2: Normalize
    normalized = normalize_leads(raw)
    print(f"[PIPELINE] normalized_count={len(normalized)}")

    # Step 3: Deduplicate
    cleaned = deduplicate_leads(normalized)
    print(f"[PIPELINE] deduped_count={len(cleaned)}")

    # Step 4: Enrich
    enriched = enrich_leads(cleaned)
    enriched = enrich_with_business_details(enriched)
    print(f"[PIPELINE] enriched_count={len(enriched)}")

    # Step 5: Score
    scored = score_leads(enriched)
    high   = sum(1 for l in scored if l.get("confidence") == "high")
    medium = sum(1 for l in scored if l.get("confidence") == "medium")
    low    = sum(1 for l in scored if l.get("confidence") == "low")
    print(f"[PIPELINE] scored_count={len(scored)} high={high} medium={medium} low={low}")

    # Step 6: Store
    stored_count = store_leads(scored, user_id, job_id)
    print(f"[PIPELINE] stored_count={stored_count}")

    # Step 7: Index
    index_leads(scored)

    # Register job in jobs table so the UI can discover this batch.
    now = datetime.now(timezone.utc)
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

    return {
        "job_id":     job_id,
        "discovered": len(raw),
        "processed":  len(scored),
        "stored":     stored_count,
    }
