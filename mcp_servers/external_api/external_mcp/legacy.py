from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as redis
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from external_mcp.config import (
    CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_WINDOW_SECONDS,
    REDIS_URL,
)

logger = structlog.get_logger()
redis_client: redis.Redis | None = None


class LegacyTransientError(RuntimeError):
    """A retryable legacy API failure."""


def get_redis_client() -> redis.Redis:
    global redis_client

    if redis_client is not None:
        return redis_client

    started_at = time.perf_counter()
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("legacy_redis_client_created", duration_ms=elapsed_ms)
    return redis_client


async def fetch_external_data(resource: str, filters: dict, tenant_id: str) -> dict:
    parsed_tenant_id = UUID(tenant_id)
    started_at = time.perf_counter()
    client = get_redis_client()

    circuit = await read_circuit_state(client, str(parsed_tenant_id))
    if circuit["state"] == "OPEN":
        cached = await read_cached_response(client, str(parsed_tenant_id), resource)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "legacy_circuit_open_returning_cache",
            tenant_id=str(parsed_tenant_id),
            resource=resource,
            cache_hit=cached is not None,
            duration_ms=elapsed_ms,
        )
        return cached or {"data": [], "source": "legacy-api-cache", "fetched_at": utc_now()}

    try:
        response = await call_legacy_api(resource, filters, str(parsed_tenant_id))
        await record_success(client, str(parsed_tenant_id), resource, response)
    except Exception:
        await record_failure(client, str(parsed_tenant_id))
        logger.exception(
            "legacy_api_fetch_failed",
            tenant_id=str(parsed_tenant_id),
            resource=resource,
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "legacy_api_fetch_complete",
        tenant_id=str(parsed_tenant_id),
        resource=resource,
        row_count=len(response["data"]),
        duration_ms=elapsed_ms,
    )
    return response


async def read_circuit_state(client: redis.Redis, tenant_id: str) -> dict:
    started_at = time.perf_counter()
    state_key = circuit_key(tenant_id, "state")
    opened_key = circuit_key(tenant_id, "opened_at")
    state = await client.get(state_key) or "CLOSED"

    if state == "OPEN":
        opened_at = float(await client.get(opened_key) or "0")
        if time.time() - opened_at >= CIRCUIT_COOLDOWN_SECONDS:
            await client.set(state_key, "HALF_OPEN")
            state = "HALF_OPEN"

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("legacy_circuit_checked", tenant_id=tenant_id, state=state, duration_ms=elapsed_ms)
    return {"state": state}


async def read_cached_response(client: redis.Redis, tenant_id: str, resource: str) -> dict | None:
    started_at = time.perf_counter()
    raw = await client.get(cache_key(tenant_id, resource))
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "legacy_cache_checked",
        tenant_id=tenant_id,
        resource=resource,
        cache_hit=raw is not None,
        duration_ms=elapsed_ms,
    )
    return json.loads(raw) if raw else None


async def record_success(client: redis.Redis, tenant_id: str, resource: str, response: dict) -> None:
    started_at = time.perf_counter()
    pipe = client.pipeline()
    pipe.set(circuit_key(tenant_id, "state"), "CLOSED")
    pipe.delete(circuit_key(tenant_id, "failures"))
    pipe.set(cache_key(tenant_id, resource), json.dumps(response), ex=300)
    await pipe.execute()
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("legacy_success_recorded", tenant_id=tenant_id, resource=resource, duration_ms=elapsed_ms)


async def record_failure(client: redis.Redis, tenant_id: str) -> None:
    started_at = time.perf_counter()
    failures_key = circuit_key(tenant_id, "failures")
    failures = await client.incr(failures_key)
    await client.expire(failures_key, CIRCUIT_WINDOW_SECONDS)
    if failures >= CIRCUIT_FAILURE_THRESHOLD:
        await client.set(circuit_key(tenant_id, "state"), "OPEN")
        await client.set(circuit_key(tenant_id, "opened_at"), str(time.time()))
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("legacy_failure_recorded", tenant_id=tenant_id, failures=failures, duration_ms=elapsed_ms)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=2),
    retry=retry_if_exception_type(LegacyTransientError),
    reraise=True,
)
async def call_legacy_api(resource: str, filters: dict, tenant_id: str) -> dict:
    started_at = time.perf_counter()
    await asyncio.sleep(0)

    if filters.get("force_failure"):
        raise LegacyTransientError("Forced retryable legacy failure.")

    response = {
        "data": legacy_rows(resource, tenant_id),
        "source": "mock-legacy-api",
        "fetched_at": utc_now(),
    }
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "legacy_api_call_complete",
        tenant_id=tenant_id,
        resource=resource,
        row_count=len(response["data"]),
        duration_ms=elapsed_ms,
    )
    return response


def legacy_rows(resource: str, tenant_id: str) -> list[dict]:
    if tenant_id == "00000000-0000-0000-0000-000000000001":
        return [
            {
                "resource": resource,
                "system": "legacy-billing",
                "sync_status": "healthy",
                "vendor": "AcmeCloud",
                "last_reconciled": "2026-05-19T18:00:00Z",
            }
        ]
    return [
        {
            "resource": resource,
            "system": "legacy-billing",
            "sync_status": "limited",
            "vendor": "BetaCloud",
            "last_reconciled": "2026-05-18T12:00:00Z",
        }
    ]


def circuit_key(tenant_id: str, suffix: str) -> str:
    return f"argus:legacy:{tenant_id}:{suffix}"


def cache_key(tenant_id: str, resource: str) -> str:
    return f"argus:legacy:{tenant_id}:cache:{resource}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
