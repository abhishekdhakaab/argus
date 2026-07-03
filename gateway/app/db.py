from __future__ import annotations

import os
import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

logger = structlog.get_logger()

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker | None = None


def get_database_url() -> str:
    return os.environ["DATABASE_URL"]


def create_engine_once() -> AsyncEngine:
    global engine, SessionLocal

    if engine is not None:
        return engine

    started_at = time.perf_counter()
    engine = create_async_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("database_engine_created", duration_ms=elapsed_ms)
    return engine


async def close_engine() -> None:
    global engine, SessionLocal

    if engine is None:
        return

    started_at = time.perf_counter()
    await engine.dispose()
    engine = None
    SessionLocal = None
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("database_engine_closed", duration_ms=elapsed_ms)


async def check_database() -> float:
    active_engine = create_engine_once()
    started_at = time.perf_counter()

    async with active_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    return round((time.perf_counter() - started_at) * 1000, 2)
