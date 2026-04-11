-- Migration : 011_experiment_variants_message
-- Target    : SQLite
-- Created   : 2026-04-10
-- Description: Adds optional message column to experiment_variants so each
--              variant can carry distinct message content for A/B testing.

ALTER TABLE experiment_variants ADD COLUMN message TEXT;
