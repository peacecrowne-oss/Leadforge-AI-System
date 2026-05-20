-- Migration : 019_add_address_column
-- Target    : SQLite
-- Created   : 2026-05-18
-- Description: Adds address column to job_leads so that physical addresses
--              collected by the enrichment pipeline (OSM addr:* tags,
--              JSON-LD PostalAddress, or scraped contact pages) can be
--              persisted and returned through the results API.
--              address_provider already exists (migration 017).
--              Nullable TEXT; existing rows get NULL automatically.

ALTER TABLE job_leads ADD COLUMN address TEXT;
