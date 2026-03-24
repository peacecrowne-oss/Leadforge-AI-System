-- Migration : 010_replies
-- Target    : SQLite + Postgres
-- Created   : 2026-03-23
-- Description: Creates the replies table for storing inbound and outbound
--              lead messages. One Lead can have many Replies (soft FK via
--              lead_id). Optional campaign_id links a reply to the campaign
--              that triggered the outreach.

-- ============================================================
-- REPLIES
-- ============================================================
CREATE TABLE IF NOT EXISTS replies (
    id           TEXT PRIMARY KEY,
    lead_id      TEXT NOT NULL,
    campaign_id  TEXT,
    user_id      TEXT NOT NULL,
    direction    TEXT NOT NULL
                     CHECK (direction IN ('inbound', 'outbound')),
    body         TEXT NOT NULL,
    sender_email TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS replies_user_lead_idx
    ON replies(user_id, lead_id);
