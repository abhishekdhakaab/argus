from __future__ import annotations

from dataclasses import dataclass

# The analytics surface is deliberately bounded to parameterized templates;
# deterministic routing keeps generated SQL out of the database boundary.


@dataclass(frozen=True)
class SqlTemplate:
    name: str
    sql: str


TOTAL_Q3_SPEND = SqlTemplate(
    name="total_q3_cloud_spend",
    sql="""
        SELECT
            period,
            SUM(amount_usd)::float AS total_spend_usd
        FROM cloud_spend
        WHERE tenant_id = $1
          AND period = '2025-Q3'
        GROUP BY period
    """,
)

Q3_SPEND_BY_PROVIDER = SqlTemplate(
    name="q3_cloud_spend_by_provider",
    sql="""
        SELECT
            provider,
            SUM(amount_usd)::float AS amount_usd
        FROM cloud_spend
        WHERE tenant_id = $1
          AND period = '2025-Q3'
        GROUP BY provider
        ORDER BY amount_usd DESC
    """,
)

Q3_VS_Q2_SPEND = SqlTemplate(
    name="q3_vs_q2_cloud_spend",
    sql="""
        SELECT
            period,
            SUM(amount_usd)::float AS total_spend_usd
        FROM cloud_spend
        WHERE tenant_id = $1
          AND period IN ('2025-Q2', '2025-Q3')
        GROUP BY period
        ORDER BY period
    """,
)


def choose_template(question: str) -> SqlTemplate:
    normalized = question.lower()
    if any(word in normalized for word in ["provider", "most expensive", "aws", "azure", "gcp"]):
        return Q3_SPEND_BY_PROVIDER
    if any(word in normalized for word in ["compare", "up", "increase", "from q2", "vs q2"]):
        return Q3_VS_Q2_SPEND
    return TOTAL_Q3_SPEND
