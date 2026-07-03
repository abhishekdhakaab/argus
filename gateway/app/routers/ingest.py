from __future__ import annotations

import os
import time
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.middleware.rate import enforce_tenant_rate_limit

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

_DOC_MCP_URL = os.getenv("DOC_MCP_URL", "http://127.0.0.1:8081")


class IngestRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    text: str = Field(min_length=1)
    source: str = Field(min_length=1)


class IngestResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    chunks_inserted: int
    source: str


@router.post("/documents", response_model=IngestResponse)
async def ingest_documents(
    payload: IngestRequest,
    tenant_id: UUID = Depends(enforce_tenant_rate_limit),
) -> IngestResponse:
    started_at = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_DOC_MCP_URL}/tools/ingest_document",
                json={
                    "text": payload.text,
                    "source": payload.source,
                    "tenant_id": str(tenant_id),
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("ingest_mcp_timeout", tenant_id=str(tenant_id), source=payload.source)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="RAG server timed out during ingest",
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.exception("ingest_mcp_error", tenant_id=str(tenant_id), source=payload.source)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RAG server returned an error",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "ingest_complete",
        tenant_id=str(tenant_id),
        source=payload.source,
        chunks_inserted=data["chunks_inserted"],
        duration_ms=elapsed_ms,
    )
    return IngestResponse(chunks_inserted=data["chunks_inserted"], source=payload.source)
