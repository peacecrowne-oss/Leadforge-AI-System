-- Migration : 012_add_lead_enrichment_columns
-- Target    : SQLite
-- Created   : 2026-05-11
-- Description: Adds enrichment columns to job_leads so that domain,
--              confidence, and reason produced by the scoring pipeline
--              can be persisted and returned through the results API.
--              All three columns are nullable TEXT so existing rows are
--              unaffected (SQLite fills them with NULL automatically).

ALTER TABLE job_leads ADD COLUMN domain     TEXT;
ALTER TABLE job_leads ADD COLUMN confidence TEXT;
ALTER TABLE job_leads ADD COLUMN reason     TEXT;
