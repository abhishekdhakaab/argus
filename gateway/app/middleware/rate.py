from __future__ import annotations

import math
import time
from uuid import UUID, uuid4

import structlog
from fastapi import Depends, HTTPException, Request, status

from app.auth.jwt import get_current_tenant
from app.cache import create_redis_once
from app.metrics import record_rate_limit_hit
from app.settings import settings

logger = structlog.get_logger()


async def enforce_tenant_rate_limit(
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
) -> UUID:
    started_at = time.perf_counter()
    tenant_key = str(tenant_id)
    redis_client = create_redis_once()

    now_ms = int(time.time() * 1000)
    window_ms = settings.rate_limit_window_seconds * 1000
    window_start_ms = now_ms - window_ms
    key = f"rate_limit:{tenant_key}"

    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start_ms)
            pipe.zcard(key)
            _, current_count = await pipe.execute()

        if current_count >= settings.rate_limit_requests:
            oldest_entries = await redis_client.zrange(key, 0, 0, withscores=True)
            oldest_score = oldest_entries[0][1] if oldest_entries else now_ms
            retry_after = max(1, math.ceil((oldest_score + window_ms - now_ms) / 1000))
            record_rate_limit_hit(tenant_key, current_count)
            logger.warning(
                "rate_limit_exceeded",
                tenant_id=tenant_key,
                current_window_count=current_count,
                retry_after=retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now_ms}:{uuid4()}"
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {member: now_ms})
            pipe.pexpire(key, window_ms)
            await pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("rate_limit_check_failed", tenant_id=tenant_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    request.state.rate_limit_count = current_count + 1
    logger.info(
        "rate_limit_check_complete",
        tenant_id=tenant_key,
        current_window_count=current_count + 1,
        duration_ms=elapsed_ms,
    )
    return tenant_id
