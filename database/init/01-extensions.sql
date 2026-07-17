-- =====================================================================
-- PostgreSQL bootstrap — runs automatically on FIRST container start
-- (mounted into /docker-entrypoint-initdb.d by docker-compose).
-- Schema itself is owned by Alembic migrations (Module 2); this file
-- only enables extensions, which require superuser privileges.
-- =====================================================================

-- gen_random_uuid() for UUID primary keys (pgcrypto is built-in on PG13+).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Trigram indexes: fast ILIKE '%keyword%' searches over transcripts and
-- meeting titles (keyword half of our hybrid search, Module 8).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
