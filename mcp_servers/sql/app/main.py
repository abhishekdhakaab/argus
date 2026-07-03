from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from sql_mcp.analytics import close_pool, query_analytics

logging.basicConfig(format="%(message)s", level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_pool()


app = FastAPI(title="Argus SQL MCP Server", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class QueryAnalyticsRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    question: str = Field(min_length=1)
    tenant_id: str = Field(min_length=36, max_length=36)


class QueryAnalyticsResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    sql: str
    rows: list[dict]
    row_count: int


@app.post("/tools/query_analytics", response_model=QueryAnalyticsResponse)
async def query_analytics_tool(payload: QueryAnalyticsRequest) -> QueryAnalyticsResponse:
    started_at = time.perf_counter()

    try:
        result = await query_analytics(payload.question, payload.tenant_id)
    except Exception as exc:
        logger.exception(
            "mcp_query_analytics_failed",
            tool="query_analytics",
            tenant_id=payload.tenant_id,
            question_len=len(payload.question),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analytics query failed",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "mcp_query_analytics_complete",
        tool="query_analytics",
        tenant_id=payload.tenant_id,
        question_len=len(payload.question),
        row_count=result["row_count"],
        duration_ms=elapsed_ms,
    )
    return QueryAnalyticsResponse(**result)
