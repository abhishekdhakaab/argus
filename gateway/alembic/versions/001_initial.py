"""Create the initial Argus database schema."""

from __future__ import annotations

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        """
        CREATE TABLE tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE query_runs (
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
        """
    )

    op.execute(
        """
        CREATE TABLE document_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            source TEXT,
            page INT,
            content TEXT NOT NULL,
            embedding vector(768),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        CREATE INDEX idx_document_chunks_embedding
        ON document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """
    )
    op.execute(
        """
        CREATE INDEX idx_document_chunks_tenant_id
        ON document_chunks (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE eval_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_ts TIMESTAMPTZ DEFAULT NOW(),
            git_sha TEXT,
            metric TEXT,
            value NUMERIC(10,4),
            threshold NUMERIC(10,4),
            passed BOOLEAN
        );
        """
    )

    op.execute(
        """
        INSERT INTO tenants (id, name)
        VALUES
            ('00000000-0000-0000-0000-000000000001', 'tenant-alpha'),
            ('00000000-0000-0000-0000-000000000002', 'tenant-beta')
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eval_results;")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_tenant_id;")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding;")
    op.execute("DROP TABLE IF EXISTS document_chunks;")
    op.execute("DROP TABLE IF EXISTS query_runs;")
    op.execute("DROP TABLE IF EXISTS tenants;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
