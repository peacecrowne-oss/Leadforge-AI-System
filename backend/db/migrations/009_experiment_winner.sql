-- Migration : 009_experiment_winner
-- Target    : SQLite + Postgres
-- Created   : 2026-03-23
-- Description: Adds winner persistence columns to the experiments table.
--              Both columns are nullable:
--                - winning_variant_id is NULL until a winner is determined
--                  (including when the result is a tie — no winner is stored).
--                - winner_basis is NULL until evaluate_winner has been called
--                  and its result persisted on experiment completion.

ALTER TABLE experiments ADD COLUMN winning_variant_id TEXT;
ALTER TABLE experiments ADD COLUMN winner_basis        TEXT;
