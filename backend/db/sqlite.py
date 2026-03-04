"""SQLite persistence layer for LeadForge.

All public functions open a new connection per call for thread safety —
sqlite3.Connection objects must not be shared across threads.

DB file: backend/leadforge.db
  (one directory above this package, resolved via __file__ so it is
   correct regardless of the working directory uvicorn is started from)

Design note on circular imports
--------------------------------
db_save_job / db_save_results receive SearchJob / Lead instances from
main.py and access their attributes via duck typing — no runtime import
of those classes is needed here.

db_load_job / db_load_results return plain dicts; the caller in main.py
is responsible for constructing the model instances. This keeps the DB
layer free of any dependency on main.py and avoids circular imports.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import sqlite3

if TYPE_CHECKING:
    # Used by type checkers / IDEs only — never executed at runtime.
    from models import Lead, SearchJob  # noqa: F401

# backend/leadforge.db — parent of db/ is backend/
DB_PATH = Path(__file__).parent.parent / "leadforge.db"


def db_connect() -> sqlite3.Connection:
    """Open a new SQLite connection with row_factory set.

    A new connection is opened per call so background-task threads and
    request-handler threads never share a connection (sqlite3 connections
    are not thread-safe by default).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_init() -> None:
    """Ensure all tables exist, migrating old job-leads schema if necessary.

    Migration strategy (idempotent):
      - If a 'leads' table with the old job-leads schema exists (has 'job_id'
        column, lacks an 'id' PK column), rename it to 'job_leads' to
        preserve all existing data.
      - Then create job_leads, users, campaigns, and the new M1 leads table
        (all with IF NOT EXISTS — safe to re-run).
    """
    with db_connect() as conn:
        # ── Safe migration: rename old job-leads 'leads' table if present ──
        _old = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leads'"
        ).fetchone()
        if _old is not None:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
            if "job_id" in cols and "id" not in cols:
                conn.execute("ALTER TABLE leads RENAME TO job_leads")

        # ── jobs (unchanged) ─────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                status        TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                request_json  TEXT NOT NULL,
                results_count INTEGER NOT NULL DEFAULT 0,
                error         TEXT
            )
        """)

        # ── job_leads (old schema, preserved for existing job data) ──────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_leads (
                job_id        TEXT NOT NULL,
                lead_id       TEXT NOT NULL,
                full_name     TEXT NOT NULL,
                title         TEXT,
                company       TEXT,
                location      TEXT,
                email         TEXT,
                linkedin_url  TEXT,
                score         REAL,
                PRIMARY KEY (job_id, lead_id)
            )
        """)

        # ── users ────────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                email       TEXT NOT NULL UNIQUE,
                full_name   TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)

        # ── campaigns ────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id                 TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                status             TEXT NOT NULL DEFAULT 'draft'
                                       CHECK (status IN ('draft','active','paused','completed','archived')),
                created_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                settings_json      TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
        """)

        # ── leads (M1) ───────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id            TEXT PRIMARY KEY,
                campaign_id   TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                status        TEXT NOT NULL DEFAULT 'new'
                                  CHECK (status IN ('new','contacted','qualified','disqualified','won','lost')),
                first_name    TEXT,
                last_name     TEXT,
                company       TEXT,
                email         TEXT,
                phone         TEXT,
                linkedin_url  TEXT,
                website_url   TEXT,
                notes         TEXT,
                meta_json     TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)

        # ── indexes ──────────────────────────────────────────────────────
        conn.execute(
            "CREATE INDEX IF NOT EXISTS campaigns_created_by_user_id_idx "
            "ON campaigns(created_by_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS leads_campaign_id_idx "
            "ON leads(campaign_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS leads_owner_user_id_idx "
            "ON leads(owner_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS leads_email_idx "
            "ON leads(email)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS leads_campaign_email_uniq "
            "ON leads(campaign_id, email) WHERE email IS NOT NULL"
        )


def db_save_job(job: SearchJob) -> None:
    """Insert or replace a job row.

    Accesses model attributes only — SearchJob is not imported at runtime.
    """
    with db_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs
                (job_id, status, created_at, updated_at, request_json, results_count, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.status,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
                job.request.model_dump_json(),
                job.results_count,
                job.error,
            ),
        )


def db_load_job(job_id: str) -> dict | None:
    """Load a raw job row from the DB; returns None if not found.

    Returns a plain dict so the caller can construct the SearchJob model
    instance without this module needing to import it.
    """
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def db_save_results(job_id: str, leads: list[Lead]) -> None:
    """Replace all leads for a job (delete-then-insert for idempotency).

    Accesses Lead attributes only — Lead is not imported at runtime.
    """
    with db_connect() as conn:
        conn.execute("DELETE FROM job_leads WHERE job_id = ?", (job_id,))
        conn.executemany(
            """
            INSERT INTO job_leads
                (job_id, lead_id, full_name, title, company,
                 location, email, linkedin_url, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    job_id, lead.id, lead.full_name, lead.title, lead.company,
                    lead.location, lead.email, lead.linkedin_url, lead.score,
                )
                for lead in leads
            ],
        )


def db_load_results(job_id: str) -> list[dict]:
    """Load raw lead rows for a job from the DB.

    Returns plain dicts (with 'id' mapped from the DB column 'lead_id')
    so the caller can construct Lead model instances without this module
    needing to import Lead.
    """
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_leads WHERE job_id = ?", (job_id,)
        ).fetchall()
    return [
        {
            "id": row["lead_id"],
            "full_name": row["full_name"],
            "title": row["title"],
            "company": row["company"],
            "location": row["location"],
            "email": row["email"],
            "linkedin_url": row["linkedin_url"],
            "score": row["score"],
        }
        for row in rows
    ]
