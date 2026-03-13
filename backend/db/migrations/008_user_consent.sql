ALTER TABLE users ADD COLUMN consent_given INTEGER DEFAULT 1;
ALTER TABLE users ADD COLUMN consent_timestamp TEXT;
