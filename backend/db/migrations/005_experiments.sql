-- Migration : 005_experiments
-- Target    : SQLite + Postgres
-- Created   : 2026-03-09
-- Description: Creates experiments and experiment_variants tables for A/B
--              testing support. One Experiment can have many
--              ExperimentVariants (one-to-many, FK with CASCADE delete).

-- ============================================================
-- EXPERIMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'running', 'paused', 'completed')),
    created_at  TEXT NOT NULL
);

-- ============================================================
-- EXPERIMENT_VARIANTS
-- ============================================================
CREATE TABLE IF NOT EXISTS experiment_variants (
    id                  TEXT PRIMARY KEY,
    experiment_id       TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    traffic_percentage  INTEGER NOT NULL DEFAULT 0
                            CHECK (traffic_percentage >= 0 AND traffic_percentage <= 100),
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS experiment_variants_experiment_id_idx
    ON experiment_variants(experiment_id);
