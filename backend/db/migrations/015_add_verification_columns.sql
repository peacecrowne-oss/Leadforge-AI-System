ALTER TABLE domain_enrichment_cache ADD COLUMN domain_verified         INTEGER;
ALTER TABLE domain_enrichment_cache ADD COLUMN mx_present              INTEGER;
ALTER TABLE domain_enrichment_cache ADD COLUMN verification_checked_at TEXT;
