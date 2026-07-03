from __future__ import annotations

import time
from uuid import UUID

import asyncpg
import structlog

from sql_mcp.config import DATABASE_URL
from sql_mcp.templates import choose_template

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        started_at = time.perf_counter()
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        logger.info("sql_pool_created", duration_ms=round((time.perf_counter() - started_at) * 1000, 2))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("sql_pool_closed")


async def query_analytics(question: str, tenant_id: str) -> dict:
    parsed_tenant_id = UUID(tenant_id)
    template = choose_template(question)
    started_at = time.perf_counter()

    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(template.sql, parsed_tenant_id)
    except Exception:
        logger.exception(
            "analytics_query_failed",
            tenant_id=str(parsed_tenant_id),
            question_len=len(question),
            template=template.name,
        )
        raise

    result_rows = [dict(row) for row in rows]
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "analytics_query_complete",
        tenant_id=str(parsed_tenant_id),
        question_len=len(question),
        template=template.name,
        row_count=len(result_rows),
        duration_ms=elapsed_ms,
    )
    return {
        "sql": compact_sql(template.sql),
        "rows": result_rows,
        "row_count": len(result_rows),
    }


def compact_sql(sql: str) -> str:
    return " ".join(sql.split())
