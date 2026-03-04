-- Migration : 001_init_core_tables
-- Target    : SQL Server (T-SQL, DATETIME2, UNIQUEIDENTIFIER)
-- Created   : 2026-02-27
-- Description: Creates dbo.users, dbo.campaigns, dbo.leads with PKs, FKs,
--              CHECK constraints, and indexes (including case-insensitive
--              collation where required).
--
-- Runner note: No GO batch separators are used. Execute as a single batch
--              or feed line-by-line to any T-SQL runner (pyodbc, sqlcmd -b, etc.).

-- ============================================================
-- UP
-- ============================================================

-- USERS
IF OBJECT_ID('dbo.users', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.users (
    id            UNIQUEIDENTIFIER NOT NULL CONSTRAINT users_pk PRIMARY KEY DEFAULT NEWID(),
    email         NVARCHAR(320)    NOT NULL,
    full_name     NVARCHAR(200)    NULL,
    created_at    DATETIME2(3)     NOT NULL CONSTRAINT users_created_at_df DEFAULT SYSUTCDATETIME(),
    updated_at    DATETIME2(3)     NOT NULL CONSTRAINT users_updated_at_df DEFAULT SYSUTCDATETIME()
  );

  CREATE UNIQUE INDEX users_email_uniq
    ON dbo.users (email COLLATE Latin1_General_100_CI_AI);
END

-- CAMPAIGNS
IF OBJECT_ID('dbo.campaigns', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.campaigns (
    id                  UNIQUEIDENTIFIER NOT NULL CONSTRAINT campaigns_pk PRIMARY KEY DEFAULT NEWID(),
    name                NVARCHAR(200)    NOT NULL,
    status              NVARCHAR(32)     NOT NULL CONSTRAINT campaigns_status_df DEFAULT N'draft',
    created_by_user_id  UNIQUEIDENTIFIER NULL,
    settings            NVARCHAR(MAX)    NULL,
    created_at          DATETIME2(3)     NOT NULL CONSTRAINT campaigns_created_at_df DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2(3)     NOT NULL CONSTRAINT campaigns_updated_at_df DEFAULT SYSUTCDATETIME(),
    CONSTRAINT campaigns_status_chk CHECK (status IN (N'draft', N'active', N'paused', N'completed', N'archived')),
    CONSTRAINT campaigns_created_by_user_fk FOREIGN KEY (created_by_user_id)
      REFERENCES dbo.users (id) ON DELETE SET NULL
  );

  CREATE INDEX campaigns_created_by_user_id_idx ON dbo.campaigns (created_by_user_id);
END

-- LEADS
IF OBJECT_ID('dbo.leads', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.leads (
    id             UNIQUEIDENTIFIER NOT NULL CONSTRAINT leads_pk PRIMARY KEY DEFAULT NEWID(),
    campaign_id    UNIQUEIDENTIFIER NOT NULL,
    owner_user_id  UNIQUEIDENTIFIER NULL,
    status         NVARCHAR(32)     NOT NULL CONSTRAINT leads_status_df DEFAULT N'new',
    first_name     NVARCHAR(100)    NULL,
    last_name      NVARCHAR(100)    NULL,
    company        NVARCHAR(200)    NULL,
    email          NVARCHAR(320)    NULL,
    phone          NVARCHAR(50)     NULL,
    linkedin_url   NVARCHAR(500)    NULL,
    website_url    NVARCHAR(500)    NULL,
    notes          NVARCHAR(MAX)    NULL,
    meta           NVARCHAR(MAX)    NULL,
    created_at     DATETIME2(3)     NOT NULL CONSTRAINT leads_created_at_df DEFAULT SYSUTCDATETIME(),
    updated_at     DATETIME2(3)     NOT NULL CONSTRAINT leads_updated_at_df DEFAULT SYSUTCDATETIME(),
    CONSTRAINT leads_status_chk CHECK (status IN (N'new', N'contacted', N'qualified', N'disqualified', N'won', N'lost')),
    CONSTRAINT leads_campaign_fk FOREIGN KEY (campaign_id)
      REFERENCES dbo.campaigns (id) ON DELETE CASCADE,
    CONSTRAINT leads_owner_user_fk FOREIGN KEY (owner_user_id)
      REFERENCES dbo.users (id) ON DELETE SET NULL
  );

  CREATE INDEX leads_campaign_id_idx   ON dbo.leads (campaign_id);
  CREATE INDEX leads_owner_user_id_idx ON dbo.leads (owner_user_id);
  CREATE INDEX leads_email_idx         ON dbo.leads (email COLLATE Latin1_General_100_CI_AI);

  CREATE UNIQUE INDEX leads_campaign_email_uniq
    ON dbo.leads (campaign_id, email COLLATE Latin1_General_100_CI_AI)
    WHERE email IS NOT NULL;
END

-- ============================================================
-- DOWN
-- ============================================================
-- Drop indexes explicitly first, then tables in reverse dependency order
-- (leads → campaigns → users) so FK constraints are satisfied.

IF OBJECT_ID('dbo.leads', 'U') IS NOT NULL
BEGIN
  DROP INDEX IF EXISTS leads_campaign_email_uniq   ON dbo.leads;
  DROP INDEX IF EXISTS leads_email_idx             ON dbo.leads;
  DROP INDEX IF EXISTS leads_owner_user_id_idx     ON dbo.leads;
  DROP INDEX IF EXISTS leads_campaign_id_idx       ON dbo.leads;
  DROP TABLE dbo.leads;
END

IF OBJECT_ID('dbo.campaigns', 'U') IS NOT NULL
BEGIN
  DROP INDEX IF EXISTS campaigns_created_by_user_id_idx ON dbo.campaigns;
  DROP TABLE dbo.campaigns;
END

IF OBJECT_ID('dbo.users', 'U') IS NOT NULL
BEGIN
  DROP INDEX IF EXISTS users_email_uniq ON dbo.users;
  DROP TABLE dbo.users;
END
