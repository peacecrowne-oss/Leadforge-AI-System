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

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
import sqlite3

from db.migrations.runner import run_migrations

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
    """Initialize the database by running all pending SQL migrations.

    Pre-migration steps (idempotent, data-safe):
      - If a 'leads' table with the old job-leads schema exists (has 'job_id'
        column, lacks an 'id' PK), rename it to 'job_leads' before migrations
        run so the new 'leads' table can be created cleanly.
      - If the 'users' table exists but is missing required columns (earlier
        dev schema), rename it to 'users_legacy_<ts>' so migrations can
        build the correct table.
    Post-migration step:
      - ALTER TABLE jobs ADD COLUMN user_id as a no-op-safe fallback for
        existing DBs where jobs was created before the column was added.
    """
    with db_connect() as conn:
        # ── Pre-migration: rename legacy 'leads' table if present ─────────
        _old = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leads'"
        ).fetchone()
        if _old is not None:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(leads)").fetchall()}
            if "job_id" in cols and "id" not in cols:
                conn.execute("ALTER TABLE leads RENAME TO job_leads")
                conn.commit()

        # ── Pre-migration: rename incomplete 'users' table if present ─────
        _USERS_REQUIRED = {"user_id", "email", "hashed_password", "role", "created_at"}
        _u = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if _u is not None:
            _ucols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
            if not _USERS_REQUIRED.issubset(_ucols):
                _legacy_name = "users_legacy_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                conn.execute(f"ALTER TABLE users RENAME TO {_legacy_name}")
                conn.commit()

        # ── Apply SQL migrations ──────────────────────────────────────────
        run_migrations(conn)

        # ── Post-migration: add user_id to pre-T13 existing jobs tables ───
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists


def db_save_job(job: SearchJob, user_id: str | None = None) -> None:
    """Upsert a job row, preserving user_id on status updates.

    On INSERT (new job_id): writes all columns including user_id.
    On CONFLICT (existing job_id, e.g. background task status update):
      updates only the mutable fields — user_id is intentionally excluded
      from DO UPDATE SET so ownership is never overwritten.

    Accesses model attributes only — SearchJob is not imported at runtime.
    """
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, status, created_at, updated_at, request_json, results_count, error, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status        = excluded.status,
                updated_at    = excluded.updated_at,
                results_count = excluded.results_count,
                error         = excluded.error
            """,
            (
                job.job_id,
                job.status,
                job.created_at.isoformat(),
                job.updated_at.isoformat(),
                job.request.model_dump_json(),
                job.results_count,
                job.error,
                user_id,
            ),
        )


def db_get_job(job_id: str, user_id: str) -> dict | None:
    """Load a job row only if owned by user_id, or if user_id is NULL (legacy).

    Returns None for both "not found" and "wrong owner" so the route layer
    cannot distinguish the two — both surface as HTTP 404.
    """
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ? AND (user_id = ? OR user_id IS NULL)",
            (job_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


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


# ── User functions ────────────────────────────────────────────────────────────

def db_create_user(
    email: str,
    hashed_password: str,
    role: str = "user",
) -> dict:
    """Insert a new user row and return a public dict (no hashed_password).

    Normalizes email to lowercase + stripped before storage.
    Generates a UUID for user_id and an ISO-8601 UTC timestamp for
    created_at.  Raises sqlite3.IntegrityError if email already exists.
    """
    email = email.strip().lower()
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, email, hashed_password, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, email, hashed_password, role, created_at),
        )
    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "created_at": created_at,
    }


def db_get_user_by_email(email: str) -> dict | None:
    """Return the user row for *email*, including hashed_password.

    Normalizes email before lookup. Returns None if no matching user exists.
    """
    email = email.strip().lower()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def db_get_user_by_id(user_id: str) -> dict | None:
    """Return the user row for *user_id*, or None if not found."""
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


# ── Campaign functions ────────────────────────────────────────────────────────

def _campaign_row(row) -> dict:
    """Convert a DB row to a public campaign dict (renames created_by_user_id → user_id)."""
    d = dict(row)
    d["user_id"] = d.pop("created_by_user_id", None)
    return d


def db_create_campaign(
    user_id: str,
    name: str,
    description: str | None = None,
    status: str = "draft",
    settings_json: str | None = None,
) -> dict:
    """Insert a new campaign row and return a public dict."""
    campaign_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO campaigns
                (id, name, description, status, created_by_user_id,
                 settings_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (campaign_id, name, description, status, user_id,
             settings_json, now, now),
        )
    return {
        "id": campaign_id,
        "name": name,
        "description": description,
        "status": status,
        "user_id": user_id,
        "settings_json": settings_json,
        "created_at": now,
        "updated_at": now,
    }


def db_list_campaigns(user_id: str) -> list[dict]:
    """Return all campaigns owned by user_id, newest first."""
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM campaigns WHERE created_by_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [_campaign_row(row) for row in rows]


def db_get_campaign(campaign_id: str, user_id: str) -> dict | None:
    """Return the campaign only if owned by user_id; None for not-found or wrong owner."""
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
    return _campaign_row(row) if row else None


def db_update_campaign(campaign_id: str, user_id: str, **fields) -> dict | None:
    """Update allowed fields on a campaign; return the updated row or None if not found/owned."""
    allowed = {"name", "description", "status", "settings_json"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return db_get_campaign(campaign_id, user_id)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [campaign_id, user_id]

    with db_connect() as conn:
        conn.execute(
            f"UPDATE campaigns SET {set_clause} WHERE id = ? AND created_by_user_id = ?",
            values,
        )
        row = conn.execute(
            "SELECT * FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
    return _campaign_row(row) if row else None


def db_delete_campaign(campaign_id: str, user_id: str) -> bool:
    """Delete a campaign owned by user_id; return True if a row was deleted."""
    with db_connect() as conn:
        cursor = conn.execute(
            "DELETE FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        )
    return cursor.rowcount > 0


# ── Campaign lead assignment functions ───────────────────────────────────────

def db_add_lead_to_campaign(
    campaign_id: str, job_id: str, lead_id: str, user_id: str
) -> dict:
    """Assign a job-search lead to a campaign.

    Verifies:
      - User owns the campaign.
      - Lead exists in a job owned by the user (or job has no owner).

    Raises ValueError if either check fails.
    Raises sqlite3.IntegrityError on duplicate (campaign_id, lead_id).
    """
    assignment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with db_connect() as conn:
        camp = conn.execute(
            "SELECT id FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
        if camp is None:
            raise ValueError("Campaign not found")

        lead = conn.execute(
            """
            SELECT jl.lead_id FROM job_leads jl
            JOIN jobs j ON j.job_id = jl.job_id
            WHERE jl.job_id = ? AND jl.lead_id = ?
              AND (j.user_id = ? OR j.user_id IS NULL)
            """,
            (job_id, lead_id, user_id),
        ).fetchone()
        if lead is None:
            raise ValueError("Lead not found or not accessible")

        conn.execute(
            """
            INSERT INTO campaign_leads (id, campaign_id, job_id, lead_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (assignment_id, campaign_id, job_id, lead_id, now),
        )

    return {
        "id": assignment_id,
        "campaign_id": campaign_id,
        "job_id": job_id,
        "lead_id": lead_id,
        "created_at": now,
    }


def db_list_campaign_leads(campaign_id: str, user_id: str) -> list[dict] | None:
    """Return all leads assigned to a campaign owned by user_id.

    Returns None if the campaign is not found or not owned by user_id
    (signals 404 to the route layer).  Returns [] if found but empty.
    """
    with db_connect() as conn:
        camp = conn.execute(
            "SELECT id FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
        if camp is None:
            return None

        rows = conn.execute(
            """
            SELECT cl.id          AS assignment_id,
                   cl.campaign_id,
                   cl.job_id,
                   cl.lead_id,
                   cl.created_at  AS assigned_at,
                   jl.full_name,
                   jl.title,
                   jl.company,
                   jl.location,
                   jl.email,
                   jl.linkedin_url,
                   jl.score
            FROM campaign_leads cl
            JOIN job_leads jl
              ON jl.job_id = cl.job_id AND jl.lead_id = cl.lead_id
            WHERE cl.campaign_id = ?
            ORDER BY cl.created_at DESC
            """,
            (campaign_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def db_remove_lead_from_campaign(
    campaign_id: str, lead_id: str, user_id: str
) -> bool:
    """Remove a lead assignment from a campaign owned by user_id.

    Returns True if a row was deleted, False if the campaign is not owned
    by the user or the assignment does not exist (both surface as 404).
    """
    with db_connect() as conn:
        camp = conn.execute(
            "SELECT id FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
        if camp is None:
            return False

        cursor = conn.execute(
            "DELETE FROM campaign_leads WHERE campaign_id = ? AND lead_id = ?",
            (campaign_id, lead_id),
        )
    return cursor.rowcount > 0
