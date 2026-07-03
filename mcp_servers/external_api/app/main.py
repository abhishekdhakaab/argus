from __future__ import annotations

import logging
import time
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from external_mcp.legacy import fetch_external_data

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

app = FastAPI(title="Argus External API MCP Server", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class FetchExternalDataRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    resource: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(min_length=36, max_length=36)


class FetchExternalDataResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    data: list[dict]
    source: str
    fetched_at: str


@app.post("/tools/fetch_external_data", response_model=FetchExternalDataResponse)
async def fetch_external_data_tool(payload: FetchExternalDataRequest) -> FetchExternalDataResponse:
    started_at = time.perf_counter()

    try:
        result = await fetch_external_data(payload.resource, payload.filters, payload.tenant_id)
    except Exception as exc:
        logger.exception(
            "mcp_fetch_external_data_failed",
            tool="fetch_external_data",
            tenant_id=payload.tenant_id,
            resource=payload.resource,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="External API fetch failed",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "mcp_fetch_external_data_complete",
        tool="fetch_external_data",
        tenant_id=payload.tenant_id,
        resource=payload.resource,
        row_count=len(result["data"]),
        duration_ms=elapsed_ms,
    )
    return FetchExternalDataResponse(**result)
