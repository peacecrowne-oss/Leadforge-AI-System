-- Migration : 017_add_provenance_columns
-- Target    : SQLite
-- Created   : 2026-05-18
-- Description: Adds field-level provenance columns to job_leads so that the
--              acquisition source of each key data point can be persisted and
--              returned through the results API.
--
--              phone_provider   — where the phone value originated
--                                 ("osm", "json_ld", "scraped_html",
--                                  "scraped_contact_page")
--              email_provider   — where the email value originated
--                                 ("csv", "osm", "hunter", "fabricated")
--              domain_provider  — where the domain value originated
--                                 ("osm", "csv")
--              address_provider — where the address value originated
--                                 ("osm", "json_ld", "scraped_html",
--                                  "scraped_contact_page")
--
--              All four columns are nullable TEXT; existing rows get NULL.

ALTER TABLE job_leads ADD COLUMN phone_provider   TEXT;
ALTER TABLE job_leads ADD COLUMN email_provider   TEXT;
ALTER TABLE job_leads ADD COLUMN domain_provider  TEXT;
ALTER TABLE job_leads ADD COLUMN address_provider TEXT;
