-- ==============================================================================
-- Context Graph – PostgreSQL 16 + pgvector Initial Schema
-- Stage 1: Relational & Vector Stores
-- Invariant: Append-only audit log; idempotent upserts for raw payloads
-- ==============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Raw source payload store
-- Each connector writes incremental read-only payloads here
CREATE TABLE IF NOT EXISTS raw_records (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    source_id VARCHAR(256) NOT NULL,
    kind VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    content_hash CHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_raw_source UNIQUE (tenant_id, source_system, source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_records_lookup
ON raw_records (tenant_id, source_system, source_id);

CREATE INDEX IF NOT EXISTS idx_raw_records_observed
ON raw_records (observed_at DESC);

-- 3. Ingestion run telemetry & watermarks
CREATE TABLE IF NOT EXISTS ingest_runs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    watermark VARCHAR(256),
    records_read INT DEFAULT 0,
    records_new INT DEFAULT 0,
    records_changed INT DEFAULT 0,
    errors INT DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingest_runs_source
ON ingest_runs (tenant_id, source_system, started_at DESC);

-- 4. Entity resolution canonical aliases
CREATE TABLE IF NOT EXISTS ci_alias (
    tenant_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    source_id VARCHAR(256) NOT NULL,
    ci_id UUID NOT NULL,
    confidence NUMERIC(3, 2) NOT NULL,
    last_verified TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_system, source_id)
);

CREATE INDEX IF NOT EXISTS idx_ci_alias_ci_id
ON ci_alias (tenant_id, ci_id);

-- 5. Entity resolution conflict queue
CREATE TABLE IF NOT EXISTS er_conflicts (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    ci_id_candidate UUID,
    source_system VARCHAR(64) NOT NULL,
    source_id VARCHAR(256) NOT NULL,
    conflict_reason TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_er_conflicts_tenant
ON er_conflicts (tenant_id, source_system);

-- 6. pgvector similarity embeddings
-- Stores embeddings of historical incidents, RCAs, and runbooks (dim: 768)
CREATE TABLE IF NOT EXISTS embeddings (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    ci_id UUID,
    service_name VARCHAR(128),
    doc_type VARCHAR(64) NOT NULL, -- 'incident', 'rca', 'runbook'
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embeddings_tenant_doc
ON embeddings (tenant_id, doc_type);

CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw
ON embeddings USING hnsw (embedding vector_cosine_ops);

-- 7. Append-only audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(256) NOT NULL,
    details JSONB,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_time
ON audit_log (tenant_id, timestamp DESC);

-- Enforce append-only property
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
