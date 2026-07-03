from __future__ import annotations

import os
import time

import redis.asyncio as redis
import structlog

logger = structlog.get_logger()

DEFAULT_REDIS_URL = "redis://localhost:6379/0"

redis_client: redis.Redis | None = None


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL)


def create_redis_once() -> redis.Redis:
    global redis_client

    if redis_client is not None:
        return redis_client

    started_at = time.perf_counter()
    redis_client = redis.from_url(get_redis_url(), decode_responses=True)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("redis_client_created", duration_ms=elapsed_ms)
    return redis_client


async def close_redis() -> None:
    global redis_client

    if redis_client is None:
        return

    started_at = time.perf_counter()
    await redis_client.aclose()
    redis_client = None
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("redis_client_closed", duration_ms=elapsed_ms)
