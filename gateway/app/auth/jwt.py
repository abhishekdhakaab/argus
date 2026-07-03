from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import text

from app.db import create_engine_once
from app.settings import settings

logger = structlog.get_logger()
bearer_scheme = HTTPBearer(auto_error=False)

# Cache key material after the first token operation.
_private_key: str | None = None
_public_key: str | None = None


def _get_private_key() -> str:
    global _private_key
    if _private_key is None:
        started_at = time.perf_counter()
        _private_key = settings.jwt_private_key_path.read_text(encoding="utf-8")
        logger.info("jwt_private_key_loaded", duration_ms=round((time.perf_counter() - started_at) * 1000, 2))
    return _private_key


def _get_public_key() -> str:
    global _public_key
    if _public_key is None:
        started_at = time.perf_counter()
        _public_key = settings.jwt_public_key_path.read_text(encoding="utf-8")
        logger.info("jwt_public_key_loaded", duration_ms=round((time.perf_counter() - started_at) * 1000, 2))
    return _public_key


def create_access_token(tenant_id: UUID) -> str:
    started_at = time.perf_counter()
    now = datetime.now(UTC)
    payload = {
        "sub": str(tenant_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
    }

    token = jwt.encode(payload, _get_private_key(), algorithm=settings.jwt_algorithm)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("access_token_created", tenant_id=str(tenant_id), duration_ms=elapsed_ms)
    return token


def decode_access_token(token: str) -> UUID:
    started_at = time.perf_counter()
    try:
        payload = jwt.decode(
            token,
            _get_public_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
        tenant_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        logger.warning("jwt_validation_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("access_token_decoded", tenant_id=str(tenant_id), duration_ms=elapsed_ms)
    return tenant_id


async def tenant_exists(tenant_id: UUID) -> bool:
    started_at = time.perf_counter()
    engine = create_engine_once()

    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        tenant_row = result.first()

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "tenant_lookup_complete",
        tenant_id=str(tenant_id),
        found=tenant_row is not None,
        duration_ms=elapsed_ms,
    )
    return tenant_row is not None


async def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UUID:
    started_at = time.perf_counter()

    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("authorization_header_missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_id = decode_access_token(credentials.credentials)
    if not await tenant_exists(tenant_id):
        logger.warning("tenant_not_found", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.tenant_id = str(tenant_id)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("current_tenant_resolved", tenant_id=str(tenant_id), duration_ms=elapsed_ms)
    return tenant_id
