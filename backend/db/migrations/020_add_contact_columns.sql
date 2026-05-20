-- Migration : 020_add_contact_columns
-- Target    : SQLite
-- Created   : 2026-05-19
-- Description: Adds key-contact fields to job_leads so that names, roles,
--              and extraction provenance gathered by the enrichment pipeline
--              can be persisted and returned through the results API.
--
--              contact_name       — extracted person name ("Jane Smith")
--              contact_role       — role label from extraction source
--                                   ("Owner", "Founder", "CEO", etc.)
--              contact_source     — extraction method
--                                   ("json_ld", "about_page", "scraped_html")
--              contact_confidence — signal strength derived from source
--                                   ("high", "medium", "low")
--
--              All four columns are nullable TEXT; existing rows get NULL.

ALTER TABLE job_leads ADD COLUMN contact_name       TEXT;
ALTER TABLE job_leads ADD COLUMN contact_role       TEXT;
ALTER TABLE job_leads ADD COLUMN contact_source     TEXT;
ALTER TABLE job_leads ADD COLUMN contact_confidence TEXT;
