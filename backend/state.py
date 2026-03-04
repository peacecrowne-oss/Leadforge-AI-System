"""Shared in-memory stores for LeadForge.

Kept in a dedicated module so both the route layer (routes/leads.py) and
any future service code can import the live dict objects without creating
a circular dependency with main.py.
"""
from models import Lead, SearchJob

JOBS: dict[str, SearchJob] = {}
RESULTS: dict[str, list[Lead]] = {}
# Maps job_id → owner user_id. None means legacy (no owner recorded).
JOB_OWNERS: dict[str, str | None] = {}
