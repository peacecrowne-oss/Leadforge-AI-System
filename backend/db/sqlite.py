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

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
import sqlite3

from db.migrations.runner import run_migrations

logger = logging.getLogger(__name__)

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
            INSERT INTO users (user_id, email, hashed_password, role, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, email, hashed_password, role, "free", created_at),
        )
    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "plan": "free",
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


def db_update_user_plan(email: str, plan: str) -> dict | None:
    """Update the plan column for the user identified by email.

    Normalizes email before lookup. Returns the updated public user dict
    (no hashed_password), or None if no matching user exists.
    """
    email = email.strip().lower()
    with db_connect() as conn:
        conn.execute(
            "UPDATE users SET plan = ? WHERE email = ?",
            (plan, email),
        )
        row = conn.execute(
            "SELECT user_id, email, role, plan, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return dict(row) if row else None


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
    start = time.monotonic()
    with db_connect() as conn:
        camp = conn.execute(
            "SELECT id FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
        if camp is None:
            return None

        lead_count = conn.execute(
            "SELECT COUNT(*) FROM campaign_leads WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
        if lead_count == 0:
            raise ValueError("Campaign has no assigned leads")

        metrics = _compute_stats(lead_count)
        now = datetime.now(timezone.utc).isoformat()

        # ── Experiment variant assignment ──────────────────────────────────
        # Load the first 'running' experiment (oldest by created_at) and
        # deterministically assign this campaign run to one of its variants.
        # Skips silently if no running experiment exists or if the experiment
        # is misconfigured (e.g. variants don't sum to 100).
        assigned_variant_id: str | None = None
        assigned_variant_name: str | None = None

        exp_row = conn.execute(
            "SELECT id FROM experiments WHERE status = 'running' "
            "ORDER BY created_at ASC LIMIT 1"
        ).fetchone()

        if exp_row is None:
            logger.info(
                "experiment_assignment_skipped campaign_id=%s reason=no_running_experiment",
                campaign_id,
            )
        else:
            variant_rows = conn.execute(
                "SELECT id, experiment_id, name, traffic_percentage, created_at "
                "FROM experiment_variants "
                "WHERE experiment_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (exp_row["id"],),
            ).fetchall()

            if variant_rows:
                # Local imports: no circular dependency risk — models.py and
                # services/ do not import db/sqlite.py.
                from models import ExperimentVariantResponse
                from services.experiment_service import assign_variant

                variants = [
                    ExperimentVariantResponse(**dict(r)) for r in variant_rows
                ]
                try:
                    selected = assign_variant(campaign_id, variants)
                    assigned_variant_id = selected.id
                    assigned_variant_name = selected.name
                    conn.execute(
                        "INSERT INTO experiment_variant_events "
                        "(id, experiment_id, variant_id, campaign_id, "
                        "event_type, created_at) "
                        "VALUES (?, ?, ?, ?, 'variant_assigned', ?)",
                        (str(uuid.uuid4()), exp_row["id"], selected.id, campaign_id, now),
                    )
                    logger.info(
                        "experiment_variant_assigned experiment_id=%s"
                        " variant_id=%s campaign_id=%s",
                        exp_row["id"],
                        selected.id,
                        campaign_id,
                    )
                except ValueError as exc:
                    logger.warning(
                        "experiment_misconfigured experiment_id=%s"
                        " campaign_id=%s error=%s",
                        exp_row["id"],
                        campaign_id,
                        exc,
                    )

        conn.execute(
            """
            INSERT INTO campaign_stats (
                campaign_id, execution_status, total_leads, processed_leads,
                sent_count, opened_count, replied_count, failed_count, last_run_at
            ) VALUES (?, 'completed', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id) DO UPDATE SET
                execution_status = 'completed',
                total_leads      = excluded.total_leads,
                processed_leads  = excluded.processed_leads,
                sent_count       = excluded.sent_count,
                opened_count     = excluded.opened_count,
                replied_count    = excluded.replied_count,
                failed_count     = excluded.failed_count,
                last_run_at      = excluded.last_run_at
            """,
            (
                campaign_id,
                metrics["total_leads"], metrics["processed_leads"],
                metrics["sent_count"], metrics["opened_count"],
                metrics["replied_count"], metrics["failed_count"],
                now,
            ),
        )
        # Advance campaign status from draft → active on first run
        conn.execute(
            "UPDATE campaigns SET status = 'active', updated_at = ? "
            "WHERE id = ? AND status = 'draft'",
            (now, campaign_id),
        )

    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "campaign_execution_completed campaign_id=%s duration_ms=%s assigned_variant_id=%s",
        campaign_id,
        duration_ms,
        assigned_variant_id,
    )
    return {
        "campaign_id": campaign_id,
        "execution_status": "completed",
        **metrics,
        "last_run_at": now,
        "assigned_variant_id": assigned_variant_id,
        "assigned_variant_name": assigned_variant_name,
    }


def db_get_campaign_stats(campaign_id: str, user_id: str) -> dict | None:
    """Return the latest stats for a campaign owned by user_id.

    Returns None if the campaign is not found, not owned, or has never been run.
    """
    with db_connect() as conn:
        camp = conn.execute(
            "SELECT id FROM campaigns WHERE id = ? AND created_by_user_id = ?",
            (campaign_id, user_id),
        ).fetchone()
        if camp is None:
            return None

        row = conn.execute(
            "SELECT * FROM campaign_stats WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
    return dict(row) if row else None


# ── Experiment functions ───────────────────────────────────────────────────────

def db_get_experiment_metrics(experiment_id: str) -> list[dict]:
    """Return per-variant metrics for a given experiment.

    Each row contains:
      variant_id        - the variant's UUID
      variant_name      - the variant's display name
      exposures         - count of 'variant_assigned' events for this variant
      distinct_campaigns - count of distinct campaigns assigned to this variant

    All variants for the experiment are returned even if they have zero
    exposures (LEFT JOIN).  Ordered by variant creation time (oldest first).
    """
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                ev.id                          AS variant_id,
                ev.name                        AS variant_name,
                COUNT(eve.id)                  AS exposures,
                COUNT(DISTINCT eve.campaign_id) AS distinct_campaigns
            FROM experiment_variants ev
            LEFT JOIN experiment_variant_events eve
                ON eve.variant_id = ev.id
                AND eve.event_type = 'variant_assigned'
            WHERE ev.experiment_id = ?
            GROUP BY ev.id, ev.name
            ORDER BY ev.created_at ASC, ev.id ASC
            """,
            (experiment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def db_get_variants_for_leads(lead_ids: list[str]) -> dict[str, str]:
    """Return a mapping of lead_id -> variant_name for leads with experiment assignments.

    Join path:
      campaign_leads.lead_id
        -> experiment_variant_events.campaign_id (event_type='variant_assigned')
        -> experiment_variants.name

    When a lead has multiple assignments the most-recent one wins.
    Returns an empty dict if lead_ids is empty or none have variant assignments.
    """
    if not lead_ids:
        return {}
    placeholders = ",".join("?" * len(lead_ids))
    with db_connect() as conn:
        rows = conn.execute(
            f"""
            SELECT cl.lead_id, ev.name AS variant_name
            FROM campaign_leads cl
            JOIN experiment_variant_events eve
              ON eve.campaign_id = cl.campaign_id
             AND eve.event_type = 'variant_assigned'
            JOIN experiment_variants ev
              ON ev.id = eve.variant_id
            WHERE cl.lead_id IN ({placeholders})
            ORDER BY eve.created_at DESC
            """,
            lead_ids,
        ).fetchall()
    # Keep only the most-recent assignment per lead (rows are DESC by created_at).
    result: dict[str, str] = {}
    for row in rows:
        if row["lead_id"] not in result:
            result[row["lead_id"]] = row["variant_name"]
    return result


def db_delete_experiment(experiment_id: str) -> bool:
    """Delete an experiment and its variants by ID.

    Returns True if a row was deleted, False if the experiment was not found.
    """
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM experiment_variants WHERE experiment_id = ?",
            (experiment_id,),
        )
        cursor = conn.execute(
            "DELETE FROM experiments WHERE id = ?",
            (experiment_id,),
        )
    return cursor.rowcount > 0


# ── Replies ───────────────────────────────────────────────────────────────────

def db_get_inbox(user_id: str) -> list[dict]:
    """Return one inbox row per lead that has replies, newest first.

    Each row contains the latest reply preview and the lead's full_name
    resolved via a LEFT JOIN on job_leads (null when not found).
    """
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.lead_id,
                r.body           AS latest_body,
                r.direction      AS latest_direction,
                r.sender_email   AS latest_sender_email,
                r.created_at     AS latest_at,
                cnt.reply_count,
                jl.full_name
            FROM replies r
            JOIN (
                SELECT lead_id,
                       COUNT(*)        AS reply_count,
                       MAX(created_at) AS max_at
                FROM replies
                WHERE user_id = ?
                GROUP BY lead_id
            ) cnt ON cnt.lead_id = r.lead_id AND cnt.max_at = r.created_at
            LEFT JOIN (
                SELECT lead_id, full_name FROM job_leads GROUP BY lead_id
            ) jl ON jl.lead_id = r.lead_id
            WHERE r.user_id = ?
            ORDER BY r.created_at DESC
            """,
            (user_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def db_get_replies_by_lead(lead_id: str, user_id: str) -> list[dict]:
    """Return all replies for a lead owned by user_id, oldest first."""
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM replies
            WHERE lead_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (lead_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def db_insert_reply(
    lead_id: str,
    user_id: str,
    body: str,
    direction: str = "inbound",
    sender_email: str | None = None,
    campaign_id: str | None = None,
) -> dict:
    """Insert a reply row and return it as a plain dict."""
    reply_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO replies
                (id, lead_id, campaign_id, user_id, direction,
                 body, sender_email, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (reply_id, lead_id, campaign_id, user_id, direction,
             body, sender_email, now),
        )
    return {
        "id": reply_id,
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "user_id": user_id,
        "direction": direction,
        "body": body,
        "sender_email": sender_email,
        "created_at": now,
    }
