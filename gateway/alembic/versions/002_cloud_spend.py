"""Add tenant-scoped cloud spend analytics data."""

from __future__ import annotations

from alembic import op

revision = "002_cloud_spend"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cloud_spend (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            period TEXT NOT NULL,
            provider TEXT NOT NULL,
            category TEXT NOT NULL,
            amount_usd NUMERIC(12,2) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX idx_cloud_spend_tenant_period
        ON cloud_spend (tenant_id, period);
        """
    )
    op.execute(
        """
        INSERT INTO cloud_spend (tenant_id, period, provider, category, amount_usd)
        VALUES
            ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'AWS', 'compute', 62000.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'Azure', 'legacy-sync', 25000.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q2', 'GCP', 'analytics', 18970.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'AWS', 'compute', 85200.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'Azure', 'legacy-sync', 31950.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'GCP', 'analytics', 17750.00),
            ('00000000-0000-0000-0000-000000000001', '2025-Q3', 'Other', 'storage', 7100.00),
            ('00000000-0000-0000-0000-000000000002', '2025-Q3', 'AWS', 'compute', 25000.00),
            ('00000000-0000-0000-0000-000000000002', '2025-Q3', 'Azure', 'legacy-sync', 12000.00)
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cloud_spend_tenant_period;")
    op.execute("DROP TABLE IF EXISTS cloud_spend;")
