from __future__ import annotations

import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.db import create_engine_once
from app.middleware.rate import enforce_tenant_rate_limit
from app.models.usage import UsageResponse

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/tenants", tags=["usage"])


@router.get("/{tenant_id}/usage", response_model=UsageResponse)
async def get_tenant_usage(
    tenant_id: UUID,
    current_tenant_id: UUID = Depends(enforce_tenant_rate_limit),
) -> UsageResponse:
    if tenant_id != current_tenant_id:
        logger.warning(
            "usage_tenant_mismatch",
            requested_tenant_id=str(tenant_id),
            current_tenant_id=str(current_tenant_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot read usage for another tenant",
        )

    try:
        usage = await load_usage_metrics(tenant_id)
    except Exception as exc:
        logger.exception("usage_metrics_failed", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load usage metrics",
        ) from exc

    return UsageResponse(**usage)


async def load_usage_metrics(tenant_id: UUID) -> dict:
    started_at = time.perf_counter()
    engine = create_engine_once()
    day_start_sql = "date_trunc('day', NOW())"

    async with engine.connect() as connection:
        totals = await connection.execute(
            text(
                f"""
                SELECT
                    COUNT(*)::int AS queries_today,
                    COALESCE(AVG(latency_ms), 0)::float AS avg_latency_ms,
                    COALESCE(
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                        0
                    )::float AS p95_latency_ms,
                    COALESCE(SUM(cost_usd), 0)::float AS total_cost_usd,
                    COALESCE(AVG(cost_usd), 0)::float AS avg_cost_per_query
                FROM query_runs
                WHERE tenant_id = :tenant_id
                  AND created_at >= {day_start_sql}
                """
            ),
            {"tenant_id": tenant_id},
        )
        tool_rows = await connection.execute(
            text(
                f"""
                SELECT tool
                FROM query_runs
                CROSS JOIN LATERAL unnest(tools_used) AS tool
                WHERE tenant_id = :tenant_id
                  AND created_at >= {day_start_sql}
                GROUP BY tool
                ORDER BY COUNT(*) DESC, tool ASC
                LIMIT 5
                """
            ),
            {"tenant_id": tenant_id},
        )

    total_row = totals.mappings().one()
    top_tools = [row.tool for row in tool_rows]
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "usage_metrics_loaded",
        tenant_id=str(tenant_id),
        queries_today=total_row["queries_today"],
        top_tools=top_tools,
        duration_ms=elapsed_ms,
    )
    return {
        "queries_today": total_row["queries_today"],
        "avg_latency_ms": round(total_row["avg_latency_ms"], 2),
        "p95_latency_ms": round(total_row["p95_latency_ms"], 2),
        "total_cost_usd": round(total_row["total_cost_usd"], 6),
        "avg_cost_per_query": round(total_row["avg_cost_per_query"], 6),
        "top_tools": top_tools,
    }
