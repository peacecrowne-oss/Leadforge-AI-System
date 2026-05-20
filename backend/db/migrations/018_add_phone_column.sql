-- Migration : 018_add_phone_column
-- Target    : SQLite
-- Created   : 2026-05-18
-- Description: Adds phone column to job_leads so that scraped/OSM phone
--              numbers collected by the enrichment pipeline can be persisted
--              and returned through the results API.
--              Nullable TEXT; existing rows get NULL automatically.

ALTER TABLE job_leads ADD COLUMN phone TEXT;
