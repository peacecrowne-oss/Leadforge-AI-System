-- Migration : 003_campaign_leads
-- Target    : SQLite + Postgres
-- Created   : 2026-03-06
-- Description: Creates the campaign_leads junction table that links job-search
--              leads to campaigns.  job_id is stored alongside lead_id because
--              job_leads uses a composite PK (job_id, lead_id); both are needed
--              to JOIN and verify lead ownership at query time.
--              UNIQUE(campaign_id, lead_id) prevents duplicate assignments.

CREATE TABLE IF NOT EXISTS campaign_leads (
    id          TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    job_id      TEXT NOT NULL,
    lead_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(campaign_id, lead_id)
);

CREATE INDEX IF NOT EXISTS campaign_leads_campaign_id_idx
    ON campaign_leads(campaign_id);
