-- Migration : 007_add_user_plan
-- Target    : SQLite
-- Created   : 2026-03-11
-- Description: Adds subscription plan column to users table. Defaults to
--              'free' for all existing and new rows.

ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free';
