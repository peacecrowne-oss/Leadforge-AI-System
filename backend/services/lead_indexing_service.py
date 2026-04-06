"""
lead_indexing_service.py

Simulated Typesense indexing layer.
Logs each lead that would be indexed. No real Typesense client yet.
"""
import logging

logger = logging.getLogger(__name__)


def index_leads(leads: list[dict]) -> None:
    """
    Simulate indexing a list of leads into Typesense.

    Logs one line per lead. Replace the log statement with a real
    Typesense upsert call when the client is available.

    Args:
        leads: List of lead dicts, each expected to have at least
               'full_name' and 'company' keys.
    """
    for lead in leads:
        full_name = lead.get("full_name") or "Unknown"
        company   = lead.get("company")   or "Unknown"
        logger.info("Indexed lead: %s (%s)", full_name, company)
