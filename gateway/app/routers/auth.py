from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text

from app.auth.jwt import bearer_scheme, create_access_token, decode_access_token, tenant_exists
from app.db import create_engine_once
from app.models.auth import TokenRequest, TokenResponse
from app.settings import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def issue_token(payload: TokenRequest) -> TokenResponse:
    started_at = time.perf_counter()

    if payload.password != settings.dev_auth_password:
        logger.warning("token_request_rejected", username=payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    engine = create_engine_once()
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id FROM tenants WHERE name = :tenant_name"),
            {"tenant_name": payload.username},
        )
        tenant_row = result.first()

    if tenant_row is None:
        logger.warning("token_request_unknown_tenant", username=payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    tenant_id = tenant_row.id
    access_token = create_access_token(tenant_id)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "token_issued",
        tenant_id=str(tenant_id),
        username=payload.username,
        duration_ms=elapsed_ms,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tenant_id = decode_access_token(credentials.credentials)
    if not await tenant_exists(tenant_id):
        logger.warning("refresh_rejected_tenant_not_found", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(tenant_id)
    logger.info("token_refreshed", tenant_id=str(tenant_id))
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_ttl_seconds,
    )
