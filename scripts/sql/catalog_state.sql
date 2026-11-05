-- Run once using an authorized PostgreSQL connection.
-- Keep this private schema outside any publicly exposed database API.
CREATE SCHEMA IF NOT EXISTS catalog_private;
REVOKE ALL ON SCHEMA catalog_private FROM PUBLIC;

CREATE TABLE IF NOT EXISTS catalog_private.objects (
    object_key text PRIMARY KEY,
    content bytea NOT NULL,
    version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_private.presence (
    email text PRIMARY KEY,
    name text NOT NULL,
    last_seen_at timestamptz NOT NULL
);

REVOKE ALL ON ALL TABLES IN SCHEMA catalog_private FROM PUBLIC;
ALTER TABLE catalog_private.objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_private.presence ENABLE ROW LEVEL SECURITY;
-- No public policies: access is exclusively through the backend database connection.
