"""PostgreSQL persistence layer for LeadForge.

Selected by db/__init__.py when DATABASE_URL starts with postgres/postgresql.

All function signatures are identical to db/sqlite.py so routes, services,
and auth code need no changes.  db_create_user re-raises sqlite3.IntegrityError
on unique violation so routes/auth.py's existing handler fires correctly.
"""
from __future__ import annotations

import os
import re
import sqlite3  # stdlib — used only to re-raise IntegrityError for compatibility
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import Lead, SearchJob  # noqa: F401

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# ── Connection ────────────────────────────────────────────────────────────────

def db_connect():
    """Open a new psycopg2 connection using DATABASE_URL.

    Returns rows as RealDictRow (dict-accessible by column name).
    Raises RuntimeError if psycopg2 is missing or DATABASE_URL is not set.
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2 is not installed. Run: pip install psycopg2-binary"
        ) from exc

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Set DATABASE_URL=postgresql://... to use the Postgres backend."
        )
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


# ── Migration runner (Postgres-specific) ──────────────────────────────────────

def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into individual executable statements.

    Splits on ';' and drops chunks that contain only whitespace/comments.
    This handles the content of 001_init_core_tables.sql without needing
    a full SQL parser — no dollar-quoted blocks or other exotic syntax exists
    in our migration files.
    """
    stmts = []
    for chunk in sql.split(";"):
        # Strip line comments then check if anything remains
        cleaned = re.sub(r"--[^\n]*", "", chunk).strip()
        if cleaned:
            stmts.append(chunk.strip())
    return stmts


def _run_migrations(conn) -> None:
    """Apply all pending *.sql migrations to Postgres, in filename order.

    Creates schema_migrations table if absent.  Idempotent: already-applied
    migrations are silently skipped.  Raises RuntimeError on failure,
    including the offending filename.
    """
    # Ensure tracking table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name       TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations")
        applied: set[str] = {row["name"] for row in cur.fetchall()}

    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        name = sql_file.name
        if name in applied:
            continue

        sql = sql_file.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                for stmt in _split_sql(sql):
                    cur.execute(stmt)
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"Migration '{name}' failed: {exc}") from exc

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (%s, %s)",
                (name, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
        print(f"[migrations] Applied: {name}")


# ── Initialization ─────────────────────────────────────────────────────────────

def db_init() -> None:
    """Initialize the Postgres database via SQL migration files."""
    conn = db_connect()
    try:
        _run_migrations(conn)
    finally:
        conn.close()


# ── Jobs ──────────────────────────────────────────────────────────────────────

def db_save_job(job: "SearchJob", user_id: str | None = None) -> None:
    """Upsert a job row, preserving user_id on status updates."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs
                    (job_id, status, created_at, updated_at, request_json,
                     results_count, error, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(job_id) DO UPDATE SET
                    status        = EXCLUDED.status,
                    updated_at    = EXCLUDED.updated_at,
                    results_count = EXCLUDED.results_count,
                    error         = EXCLUDED.error
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
        conn.commit()
    finally:
        conn.close()


def db_get_job(job_id: str, user_id: str) -> dict | None:
    """Load a job only if owned by user_id, or if user_id is NULL (legacy)."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM jobs WHERE job_id = %s AND (user_id = %s OR user_id IS NULL)",
                (job_id, user_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def db_load_job(job_id: str) -> dict | None:
    """Load a raw job row; returns None if not found."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


# ── Leads ─────────────────────────────────────────────────────────────────────

def db_save_results(job_id: str, leads: "list[Lead]") -> None:
    """Replace all leads for a job (delete-then-insert for idempotency)."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM job_leads WHERE job_id = %s", (job_id,))
            if leads:
                cur.executemany(
                    """
                    INSERT INTO job_leads
                        (job_id, lead_id, full_name, title, company,
                         location, email, linkedin_url, score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            job_id, lead.id, lead.full_name, lead.title,
                            lead.company, lead.location, lead.email,
                            lead.linkedin_url, lead.score,
                        )
                        for lead in leads
                    ],
                )
        conn.commit()
    finally:
        conn.close()


def db_load_results(job_id: str) -> list[dict]:
    """Load raw lead rows for a job; returns plain dicts with 'id' mapped from lead_id."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM job_leads WHERE job_id = %s", (job_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
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


# ── Users ─────────────────────────────────────────────────────────────────────

def db_create_user(
    email: str,
    hashed_password: str,
    role: str = "user",
) -> dict:
    """Insert a new user and return a public dict (no hashed_password).

    Raises sqlite3.IntegrityError on duplicate email so routes/auth.py's
    existing exception handler fires correctly regardless of backend.
    """
    email = email.strip().lower()
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, email, hashed_password, role, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, email, hashed_password, role, created_at),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        # Translate Postgres unique violation → sqlite3.IntegrityError so
        # routes/auth.py's existing `except sqlite3.IntegrityError` handler works.
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise sqlite3.IntegrityError(str(exc)) from exc
        raise
    finally:
        conn.close()
    return {"user_id": user_id, "email": email, "role": role, "created_at": created_at}


def db_get_user_by_email(email: str) -> dict | None:
    """Return the user row for email (including hashed_password), or None."""
    email = email.strip().lower()
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def db_get_user_by_id(user_id: str) -> dict | None:
    """Return the user row for user_id, or None if not found."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


# ── Campaign functions ────────────────────────────────────────────────────────

def _campaign_row(row: dict) -> dict:
    """Rename created_by_user_id → user_id in a Postgres RealDictRow."""
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
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO campaigns
                    (id, name, description, status, created_by_user_id,
                     settings_json, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (campaign_id, name, description, status, user_id,
                 settings_json, now, now),
            )
        conn.commit()
    finally:
        conn.close()
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
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM campaigns WHERE created_by_user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_campaign_row(row) for row in rows]


def db_get_campaign(campaign_id: str, user_id: str) -> dict | None:
    """Return the campaign only if owned by user_id; None for not-found or wrong owner."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return _campaign_row(row) if row else None


def db_update_campaign(campaign_id: str, user_id: str, **fields) -> dict | None:
    """Update allowed fields on a campaign; return the updated row or None if not found/owned."""
    allowed = {"name", "description", "status", "settings_json"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return db_get_campaign(campaign_id, user_id)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [campaign_id, user_id]

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE campaigns SET {set_clause} WHERE id = %s AND created_by_user_id = %s",
                values,
            )
            cur.execute(
                "SELECT * FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    return _campaign_row(row) if row else None


def db_delete_campaign(campaign_id: str, user_id: str) -> bool:
    """Delete a campaign owned by user_id; return True if a row was deleted."""
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return deleted


# ── Campaign lead assignment functions ───────────────────────────────────────

def db_add_lead_to_campaign(
    campaign_id: str, job_id: str, lead_id: str, user_id: str
) -> dict:
    """Assign a job-search lead to a campaign.

    Raises ValueError if campaign not found or lead not accessible.
    Raises sqlite3.IntegrityError on duplicate (campaign_id, lead_id).
    """
    assignment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            if cur.fetchone() is None:
                raise ValueError("Campaign not found")

            cur.execute(
                """
                SELECT jl.lead_id FROM job_leads jl
                JOIN jobs j ON j.job_id = jl.job_id
                WHERE jl.job_id = %s AND jl.lead_id = %s
                  AND (j.user_id = %s OR j.user_id IS NULL)
                """,
                (job_id, lead_id, user_id),
            )
            if cur.fetchone() is None:
                raise ValueError("Lead not found or not accessible")

            cur.execute(
                """
                INSERT INTO campaign_leads (id, campaign_id, job_id, lead_id, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (assignment_id, campaign_id, job_id, lead_id, now),
            )
        conn.commit()
    except ValueError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise sqlite3.IntegrityError(str(exc)) from exc
        raise
    finally:
        conn.close()

    return {
        "id": assignment_id,
        "campaign_id": campaign_id,
        "job_id": job_id,
        "lead_id": lead_id,
        "created_at": now,
    }


def db_list_campaign_leads(campaign_id: str, user_id: str) -> list[dict] | None:
    """Return all leads assigned to a campaign owned by user_id.

    Returns None if campaign not found/not owned (→ 404). Returns [] if empty.
    """
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            if cur.fetchone() is None:
                return None

            cur.execute(
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
                WHERE cl.campaign_id = %s
                ORDER BY cl.created_at DESC
                """,
                (campaign_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def db_remove_lead_from_campaign(
    campaign_id: str, lead_id: str, user_id: str
) -> bool:
    """Remove a lead assignment from a campaign owned by user_id.

    Returns True if deleted, False if campaign not owned or assignment missing.
    """
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            if cur.fetchone() is None:
                return False

            cur.execute(
                "DELETE FROM campaign_leads WHERE campaign_id = %s AND lead_id = %s",
                (campaign_id, lead_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return deleted


# ── Campaign execution functions ──────────────────────────────────────────────

def _compute_stats(total_leads: int) -> dict:
    """Deterministic engagement metrics for a given lead count.

    Uses integer arithmetic so results are stable for the same N:
      - sent      = total_leads
      - opened    = floor(sent   * 3 / 5)   ~60%
      - replied   = floor(opened * 3 / 10)  ~30% of opens
      - failed    = 0
    """
    sent = total_leads
    opened = (sent * 3) // 5
    replied = (opened * 3) // 10
    return {
        "total_leads": total_leads,
        "processed_leads": total_leads,
        "sent_count": sent,
        "opened_count": opened,
        "replied_count": replied,
        "failed_count": 0,
    }


def db_run_campaign(campaign_id: str, user_id: str) -> dict | None:
    """Execute a campaign and persist stats.

    Returns None if the campaign is not found or not owned by user_id.
    Raises ValueError if the campaign has no assigned leads.
    Returns the stats dict on success.
    """
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            if cur.fetchone() is None:
                return None

            cur.execute(
                "SELECT COUNT(*) AS n FROM campaign_leads WHERE campaign_id = %s",
                (campaign_id,),
            )
            lead_count = cur.fetchone()["n"]
            if lead_count == 0:
                raise ValueError("Campaign has no assigned leads")

            metrics = _compute_stats(lead_count)
            now = datetime.now(timezone.utc).isoformat()

            cur.execute(
                """
                INSERT INTO campaign_stats (
                    campaign_id, execution_status, total_leads, processed_leads,
                    sent_count, opened_count, replied_count, failed_count, last_run_at
                ) VALUES (%s, 'completed', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (campaign_id) DO UPDATE SET
                    execution_status = 'completed',
                    total_leads      = EXCLUDED.total_leads,
                    processed_leads  = EXCLUDED.processed_leads,
                    sent_count       = EXCLUDED.sent_count,
                    opened_count     = EXCLUDED.opened_count,
                    replied_count    = EXCLUDED.replied_count,
                    failed_count     = EXCLUDED.failed_count,
                    last_run_at      = EXCLUDED.last_run_at
                """,
                (
                    campaign_id,
                    metrics["total_leads"], metrics["processed_leads"],
                    metrics["sent_count"], metrics["opened_count"],
                    metrics["replied_count"], metrics["failed_count"],
                    now,
                ),
            )
            cur.execute(
                "UPDATE campaigns SET status = 'active', updated_at = %s "
                "WHERE id = %s AND status = 'draft'",
                (now, campaign_id),
            )
        conn.commit()
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "campaign_id": campaign_id,
        "execution_status": "completed",
        **metrics,
        "last_run_at": now,
    }


def db_get_campaign_stats(campaign_id: str, user_id: str) -> dict | None:
    """Return the latest stats for a campaign owned by user_id.

    Returns None if the campaign is not found, not owned, or has never been run.
    """
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM campaigns WHERE id = %s AND created_by_user_id = %s",
                (campaign_id, user_id),
            )
            if cur.fetchone() is None:
                return None

            cur.execute(
                "SELECT * FROM campaign_stats WHERE campaign_id = %s",
                (campaign_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None
