CREATE TABLE IF NOT EXISTS domain_enrichment_cache (
    domain              TEXT PRIMARY KEY,
    phone               TEXT,
    phone_source        TEXT,
    address             TEXT,
    address_source      TEXT,
    contact_name        TEXT,
    contact_name_source TEXT,
    cached_at           TEXT NOT NULL
);
