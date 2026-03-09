-- Migration : 006_experiment_variant_events
-- Target    : SQLite + Postgres
-- Created   : 2026-03-09
-- Description: Creates experiment_variant_events table — an append-only event
--              log recording each campaign-run assignment to an experiment
--              variant.  Provides the raw rows needed for per-variant metrics
--              aggregation (open rates, reply rates, conversions) in later steps.
--              Indexes on experiment_id, variant_id, and campaign_id allow
--              efficient GROUP BY queries without full-table scans.

CREATE TABLE IF NOT EXISTS experiment_variant_events (
    id            TEXT NOT NULL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    variant_id    TEXT NOT NULL,
    campaign_id   TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS evte_experiment_id_idx
    ON experiment_variant_events(experiment_id);

CREATE INDEX IF NOT EXISTS evte_variant_id_idx
    ON experiment_variant_events(variant_id);

CREATE INDEX IF NOT EXISTS evte_campaign_id_idx
    ON experiment_variant_events(campaign_id);
