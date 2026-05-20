-- Migration : 016_add_provider_columns
-- Target    : SQLite
-- Created   : 2026-05-18
-- Description: Adds provider attribution columns to job_leads so that
--              acquisition source metadata is persisted and returned through
--              the results API.
--
--              provider              — acquisition source name ("osm", "csv", …)
--              provider_entity_type  — source-specific entity class
--                                      ("node", "way", "relation" for OSM)
--              provider_confidence   — source-level data-completeness signal
--                                      ("low", "medium", "high")
--
--              All three columns are nullable TEXT so that existing rows are
--              unaffected (SQLite fills them with NULL automatically).

ALTER TABLE job_leads ADD COLUMN provider             TEXT;
ALTER TABLE job_leads ADD COLUMN provider_entity_type TEXT;
ALTER TABLE job_leads ADD COLUMN provider_confidence  TEXT;
