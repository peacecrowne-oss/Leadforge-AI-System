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
from services.lead_discovery_service  import fetch_leads_from_api
from services.lead_processing_service import normalize_leads, deduplicate_leads
from services.lead_enrichment_service import enrich_leads
from services.lead_scoring_service    import score_leads
from services.lead_storage_service    import store_leads
from services.lead_indexing_service   import index_leads


def run_pipeline(query: str, location: str, user_id: str) -> dict:
    """
    Run the full lead pipeline for the given search parameters.

    Args:
        query:    Keyword to match against title / company.
        location: Location filter string.
        user_id:  ID of the requesting user (used for DB storage).

    Returns:
        Summary dict:
          {
            "discovered": int,  # raw leads returned by the API
            "processed":  int,  # leads remaining after dedup/enrich/score
            "stored":     int,  # leads actually inserted into the DB
          }
    """
    # Step 1: Discover
    raw = fetch_leads_from_api(query, location)

    # Step 2: Normalize
    normalized = normalize_leads(raw)

    # Step 3: Deduplicate
    cleaned = deduplicate_leads(normalized)

    # Step 4: Enrich
    enriched = enrich_leads(cleaned)

    # Step 5: Score
    scored = score_leads(enriched)

    # Step 6: Store
    stored_count = store_leads(scored, user_id)

    # Step 7: Index
    index_leads(scored)

    return {
        "discovered": len(raw),
        "processed":  len(scored),
        "stored":     stored_count,
    }
