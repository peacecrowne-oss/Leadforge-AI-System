"""Tiny idempotent SQLite migration runner for LeadForge.

Usage (called once at startup from db.sqlite.db_init):
    from db.migrations.runner import run_migrations
    with db_connect() as conn:
        run_migrations(conn)

Behaviour:
  - Creates schema_migrations(name TEXT PK, applied_at TEXT) if absent.
  - Reads all *.sql files in this directory, sorted by filename.
  - For each file not yet recorded in schema_migrations, executes its full
    SQL content via executescript() then records the filename + timestamp.
  - Already-applied migrations are silently skipped — fully idempotent.
  - Raises RuntimeError (wrapping the original sqlite3.Error) on failure,
    including the offending filename so the cause is immediately clear.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending *.sql migrations, in filename order.

    Safe to call multiple times: already-applied migrations are skipped.
    Raises RuntimeError on the first migration that fails.
    """
    # Ensure tracking table exists (DDL — executescript commits first).
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name       TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
    """)

    applied: set[str] = {
        row[0]
        for row in conn.execute("SELECT name FROM schema_migrations").fetchall()
    }

    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        name = sql_file.name
        if name in applied:
            continue  # already applied — skip

        sql = sql_file.read_text(encoding="utf-8")
        try:
            # executescript() issues an implicit COMMIT before running, so
            # it is safe for DDL even when called inside a transaction.
            conn.executescript(sql)
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"Migration '{name}' failed: {exc}"
            ) from exc

        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        print(f"[migrations] Applied: {name}")
