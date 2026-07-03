-- Local bootstrap schema matching Alembic migrations 001 and 002.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_runs (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    query TEXT NOT NULL,
    answer TEXT,
    plan JSONB,
    input_tokens INT,
    output_tokens INT,
    cost_usd NUMERIC(10,6),
    latency_ms INT,
    tools_used TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    source TEXT,
    page INT,
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_id
    ON document_chunks (tenant_id);

CREATE TABLE IF NOT EXISTS eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_ts TIMESTAMPTZ DEFAULT NOW(),
    git_sha TEXT,
    metric TEXT,
    value NUMERIC(10,4),
    threshold NUMERIC(10,4),
    passed BOOLEAN
);

CREATE TABLE IF NOT EXISTS cloud_spend (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    period TEXT NOT NULL,
    provider TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_usd NUMERIC(12,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cloud_spend_tenant_period
    ON cloud_spend (tenant_id, period);

INSERT INTO tenants (id, name) VALUES
    ('00000000-0000-0000-0000-000000000001', 'tenant-alpha'),
    ('00000000-0000-0000-0000-000000000002', 'tenant-beta')
ON CONFLICT (id) DO NOTHING;

INSERT INTO cloud_spend (tenant_id, period, provider, category, amount_usd) VALUES
    ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'AWS',   'compute',    62000.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'Azure', 'legacy-sync',25000.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'GCP',   'analytics',  18970.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'AWS',   'compute',    85200.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'Azure', 'legacy-sync',31950.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'GCP',   'analytics',  17750.00),
    ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'Other', 'storage',     7100.00),
    ('00000000-0000-0000-0000-000000000002', '2025-Q3', 'AWS',   'compute',    25000.00),
    ('00000000-0000-0000-0000-000000000002', '2025-Q3', 'Azure', 'legacy-sync',12000.00)
ON CONFLICT DO NOTHING;
