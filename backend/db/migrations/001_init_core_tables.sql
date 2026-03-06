-- Migration : 001_init_core_tables
-- Target    : SQLite
-- Created   : 2026-03-06
-- Description: Creates users, jobs, job_leads, campaigns, leads tables
--              with PKs, FKs, CHECK constraints, and indexes.
--              All statements use IF NOT EXISTS so this script is safe
--              to execute on a database that already has some/all tables.

-- ============================================================
-- USERS
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TEXT NOT NULL
);

-- ============================================================
-- JOBS
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    request_json  TEXT NOT NULL,
    results_count INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    user_id       TEXT
);

-- ============================================================
-- JOB_LEADS  (legacy result rows, one per lead per job)
-- ============================================================
CREATE TABLE IF NOT EXISTS job_leads (
    job_id       TEXT NOT NULL,
    lead_id      TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    title        TEXT,
    company      TEXT,
    location     TEXT,
    email        TEXT,
    linkedin_url TEXT,
    score        REAL,
    PRIMARY KEY (job_id, lead_id)
);

-- ============================================================
-- CAMPAIGNS
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft','active','paused','completed','archived')),
    created_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    settings_json      TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS campaigns_created_by_user_id_idx
    ON campaigns(created_by_user_id);

-- ============================================================
-- LEADS  (M1 CRM leads, linked to campaigns)
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
    id            TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    owner_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'new'
                      CHECK (status IN ('new','contacted','qualified','disqualified','won','lost')),
    first_name    TEXT,
    last_name     TEXT,
    company       TEXT,
    email         TEXT,
    phone         TEXT,
    linkedin_url  TEXT,
    website_url   TEXT,
    notes         TEXT,
    meta_json     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS leads_campaign_id_idx
    ON leads(campaign_id);

CREATE INDEX IF NOT EXISTS leads_owner_user_id_idx
    ON leads(owner_user_id);

CREATE INDEX IF NOT EXISTS leads_email_idx
    ON leads(email);

CREATE UNIQUE INDEX IF NOT EXISTS leads_campaign_email_uniq
    ON leads(campaign_id, email) WHERE email IS NOT NULL;
