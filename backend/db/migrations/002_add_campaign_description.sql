-- Migration : 002_add_campaign_description
-- Target    : SQLite + Postgres
-- Created   : 2026-03-06
-- Description: Adds optional free-text description column to campaigns table.

ALTER TABLE campaigns ADD COLUMN description TEXT;
