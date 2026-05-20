-- Migration : 021_add_identity_type
-- Target    : SQLite
-- Created   : 2026-05-19
-- Description: Adds identity_type to job_leads so the pipeline can tag each
--              lead as 'person', 'business', or 'unknown' using lightweight
--              heuristics applied at normalization time.
--
--              identity_type — 'person' | 'business' | 'unknown' | NULL
--
--              NULL means the row predates this migration; the API and UI
--              treat NULL identically to 'unknown'.

ALTER TABLE job_leads ADD COLUMN identity_type TEXT;
