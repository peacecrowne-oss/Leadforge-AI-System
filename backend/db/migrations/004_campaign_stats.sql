-- Migration : 004_campaign_stats
-- Target    : SQLite + Postgres
-- Created   : 2026-03-06
-- Description: Adds campaign_stats table — one persistent stats row per
--              campaign, upserted on each run.  Tracks execution lifecycle
--              and deterministic engagement metrics.
--              ON DELETE CASCADE keeps cleanup automatic when a campaign
--              is deleted.

CREATE TABLE IF NOT EXISTS campaign_stats (
    campaign_id      TEXT PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
    execution_status TEXT NOT NULL DEFAULT 'pending',
    total_leads      INTEGER NOT NULL DEFAULT 0,
    processed_leads  INTEGER NOT NULL DEFAULT 0,
    sent_count       INTEGER NOT NULL DEFAULT 0,
    opened_count     INTEGER NOT NULL DEFAULT 0,
    replied_count    INTEGER NOT NULL DEFAULT 0,
    failed_count     INTEGER NOT NULL DEFAULT 0,
    last_run_at      TEXT
);
