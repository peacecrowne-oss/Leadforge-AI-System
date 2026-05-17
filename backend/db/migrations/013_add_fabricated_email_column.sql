-- Migration : 013_add_fabricated_email_column
-- Target    : SQLite
-- Created   : 2026-05-11
-- Description: Adds fabricated_email column to job_leads so the enrichment
--              flag set by lead_enrichment_service is persisted and returned
--              through the results API.
--              INTEGER nullable: NULL = not set / real email, 1 = fabricated.
--              Existing rows are unaffected (SQLite fills them with NULL).

ALTER TABLE job_leads ADD COLUMN fabricated_email INTEGER;
