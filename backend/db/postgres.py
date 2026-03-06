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
