from __future__ import annotations

import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends

from app.middleware.rate import enforce_tenant_rate_limit
from app.models.health import TenantHealthResponse

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=TenantHealthResponse)
async def tenant_health(
    tenant_id: UUID = Depends(enforce_tenant_rate_limit),
) -> TenantHealthResponse:
    started_at = time.perf_counter()
    response = TenantHealthResponse(status="ok", tenant_id=str(tenant_id))
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("tenant_health_complete", tenant_id=str(tenant_id), duration_ms=elapsed_ms)
    return response
