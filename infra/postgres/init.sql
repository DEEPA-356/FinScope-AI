-- PostgreSQL initialization script
-- Runs once when the container is first created.
-- Alembic manages the schema; this only handles extensions
-- and database-level setup.

-- Required for UUID primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Required for vector search (Phase 9 — RAG chatbot)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Required for MLflow backend store
-- (MLflow handles its own schema via migrations)
