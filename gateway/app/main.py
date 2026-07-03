from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import close_redis, create_redis_once
from app.db import check_database, close_engine, create_engine_once
from app.models.health import PublicHealthResponse
from app.routers import auth, health as health_router, ingest, query, usage

PROCESS_STARTED_AT = time.perf_counter()
first_request_logged = False


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_engine_once()
    create_redis_once()
    logger.info("gateway_startup_complete", version="0.1.0")
    try:
        yield
    finally:
        await close_redis()
        await close_engine()


app = FastAPI(title="Argus Gateway", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health_router.router)
app.include_router(query.router)
app.include_router(usage.router)
app.include_router(ingest.router)

# Instrumentation needs the complete route table.
from app.otel import setup_otel  # noqa: E402
setup_otel(app)


@app.get("/health", response_model=PublicHealthResponse)
async def health() -> PublicHealthResponse:
    global first_request_logged

    request_started_at = time.perf_counter()
    if not first_request_logged:
        first_request_logged = True
        startup_ms = round((request_started_at - PROCESS_STARTED_AT) * 1000, 2)
        logger.info("first_request_served", startup_ms=startup_ms)

    try:
        db_latency_ms = await check_database()
        db_status = "ok"
        detail = None
    except Exception as exc:
        logger.exception("database_health_check_failed")
        db_latency_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
        db_status = "error"
        detail = str(exc)

    duration_ms = round((time.perf_counter() - request_started_at) * 1000, 2)
    logger.info(
        "health_check_complete",
        db=db_status,
        db_latency_ms=db_latency_ms,
        duration_ms=duration_ms,
    )

    return PublicHealthResponse(
        status="ok",
        version="0.1.0",
        db=db_status,
        detail=detail,
    )
