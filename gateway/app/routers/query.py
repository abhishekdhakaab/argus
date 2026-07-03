from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import create_engine_once
from app.middleware.rate import enforce_tenant_rate_limit
from app.models.query import QueryRequest, QueryRunResponse

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.graph import build_agent_graph
from agent.state import AgentState

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["query"])
query_graph = build_agent_graph()


@router.post("/query")
async def create_query_run(
    payload: QueryRequest,
    tenant_id: UUID = Depends(enforce_tenant_rate_limit),
) -> StreamingResponse:
    run_id = uuid4()
    engine = create_engine_once()

    try:
        await insert_query_run(engine, run_id, tenant_id, payload.query)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "query_stream_setup_failed",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
            query_len=len(payload.query),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not complete query",
        ) from exc

    return StreamingResponse(
        event_generator(run_id, tenant_id, payload.query, engine),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def event_generator(
    run_id: UUID,
    tenant_id: UUID,
    query: str,
    engine: AsyncEngine,
) -> AsyncIterator[str]:
    started_at = time.perf_counter()

    # Node events expose the state needed for the final audit record.
    collected: dict[str, Any] = {
        "plan": [],
        "doc_context": [],
        "sql_context": [],
        "api_context": [],
        "answer": "",
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
    }

    _START_MESSAGES: dict[str, str] = {
        "planner":      "Planning query...",
        "doc_retrieval": "Searching documents...",
        "sql_retrieval": "Querying analytics...",
        "api_retrieval": "Fetching external data...",
        "synthesis":    "Synthesizing answer...",
    }
    _RETRIEVAL_FIELD: dict[str, str] = {
        "doc_retrieval": "doc_context",
        "sql_retrieval": "sql_context",
        "api_retrieval": "api_context",
    }
    _RETRIEVAL_MSG: dict[str, str] = {
        "doc_retrieval": "Found {n} chunks",
        "sql_retrieval": "Found {n} analytics result sets",
        "api_retrieval": "Fetched {n} external result sets",
    }

    try:
        # Graph events provide live step updates. Answer tokens are replayed after
        # synthesis because the node currently returns one complete string.
        async for event in query_graph.astream_events(
            build_initial_state(query, tenant_id, run_id),
            version="v2",
        ):
            kind = event["event"]
            name = event.get("name", "")
            output: dict[str, Any] = (event.get("data") or {}).get("output") or {}

            if kind == "on_chain_start" and name in _START_MESSAGES:
                yield sse_event("step", {"node": name, "message": _START_MESSAGES[name]})

            elif kind == "on_chain_end":
                if name == "planner" and isinstance(output.get("plan"), list):
                    collected["plan"] = output["plan"]

                elif name in _RETRIEVAL_FIELD:
                    field = _RETRIEVAL_FIELD[name]
                    ctx = output.get(field) or []
                    collected[field] = ctx
                    yield sse_event("step", {"node": name, "message": _RETRIEVAL_MSG[name].format(n=len(ctx))})

                elif name == "synthesis":
                    if isinstance(output.get("answer"), str):
                        collected["answer"] = output["answer"]
                    if isinstance(output.get("token_usage"), dict):
                        collected["token_usage"] = output["token_usage"]

        latency_ms = int(round((time.perf_counter() - started_at) * 1000))
        token_usage = collected["token_usage"]
        tools_used = actual_tools_used(collected)

        await update_query_run(
            engine=engine,
            run_id=run_id,
            tenant_id=tenant_id,
            answer=collected["answer"],
            plan=collected["plan"],
            token_usage=token_usage,
            latency_ms=latency_ms,
            tools_used=tools_used,
        )

        for token in answer_tokens(collected["answer"]):
            yield sse_event("token", token)
            await asyncio.sleep(0)

        yield sse_event(
            "done",
            {
                "run_id": str(run_id),
                "cost_usd": token_usage.get("cost_usd", 0),
                "latency_ms": latency_ms,
            },
        )

        logger.info(
            "query_stream_complete",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
            query_len=len(query),
            answer_len=len(collected["answer"]),
            tools_used=tools_used,
            input_tokens=token_usage.get("input_tokens", 0),
            output_tokens=token_usage.get("output_tokens", 0),
            cost_usd=token_usage.get("cost_usd", 0),
            latency_ms=latency_ms,
        )

    except Exception:
        logger.exception(
            "query_stream_failed",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
            query_len=len(query),
        )
        raise


def build_initial_state(query: str, tenant_id: UUID, run_id: UUID) -> AgentState:
    return {
        "query": query,
        "tenant_id": str(tenant_id),
        "plan": [],
        "doc_context": [],
        "sql_context": [],
        "api_context": [],
        "answer": "",
        "run_id": str(run_id),
        "token_usage": {},
    }


async def insert_query_run(
    engine: AsyncEngine,
    run_id: UUID,
    tenant_id: UUID,
    query: str,
) -> None:
    started_at = time.perf_counter()

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO query_runs (id, tenant_id, query)
                    VALUES (:run_id, :tenant_id, :query)
                    """
                ),
                {
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "query": query,
                },
            )
    except Exception:
        logger.exception(
            "query_run_insert_failed",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "query_run_created",
        run_id=str(run_id),
        tenant_id=str(tenant_id),
        query_len=len(query),
        duration_ms=elapsed_ms,
    )


async def update_query_run(
    engine: AsyncEngine,
    run_id: UUID,
    tenant_id: UUID,
    answer: str,
    plan: list[dict],
    token_usage: dict,
    latency_ms: int,
    tools_used: list[str],
) -> None:
    started_at = time.perf_counter()

    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE query_runs
                    SET answer = :answer,
                        plan = CAST(:plan AS JSONB),
                        input_tokens = :input_tokens,
                        output_tokens = :output_tokens,
                        cost_usd = :cost_usd,
                        latency_ms = :latency_ms,
                        tools_used = CAST(:tools_used AS TEXT[])
                    WHERE id = :run_id
                      AND tenant_id = :tenant_id
                    """
                ),
                {
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "answer": answer,
                    "plan": json.dumps(plan),
                    "input_tokens": token_usage["input_tokens"],
                    "output_tokens": token_usage["output_tokens"],
                    "cost_usd": token_usage["cost_usd"],
                    "latency_ms": latency_ms,
                    "tools_used": tools_used,
                },
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Expected to update 1 query_run row, updated {result.rowcount}.")
    except Exception:
        logger.exception(
            "query_run_update_failed",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "query_run_updated",
        run_id=str(run_id),
        tenant_id=str(tenant_id),
        answer_len=len(answer),
        input_tokens=token_usage["input_tokens"],
        output_tokens=token_usage["output_tokens"],
        cost_usd=token_usage["cost_usd"],
        latency_ms=latency_ms,
        tools_used=tools_used,
        duration_ms=elapsed_ms,
    )


def actual_tools_used(result: dict) -> list[str]:
    tools: list[str] = []
    if result["doc_context"]:
        tools.append("search_documents")
    if result["sql_context"]:
        tools.append("query_analytics")
    if result["api_context"]:
        tools.append("fetch_external_data")
    return tools



@router.get("/query/{run_id}", response_model=QueryRunResponse)
async def get_query_run(
    run_id: UUID,
    tenant_id: UUID = Depends(enforce_tenant_rate_limit),
) -> QueryRunResponse:
    engine = create_engine_once()
    async with engine.connect() as connection:
        row = await connection.execute(
            text(
                """
                SELECT id, query, answer, cost_usd, latency_ms, tools_used
                FROM query_runs
                WHERE id = :run_id AND tenant_id = :tenant_id
                """
            ),
            {"run_id": run_id, "tenant_id": tenant_id},
        )
        record = row.mappings().first()

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return QueryRunResponse(
        run_id=str(record["id"]),
        query=record["query"],
        answer=record["answer"],
        status="complete" if record["answer"] else "pending",
        cost_usd=float(record["cost_usd"]) if record["cost_usd"] is not None else None,
        latency_ms=record["latency_ms"],
        tools_used=list(record["tools_used"]) if record["tools_used"] else None,
    )


def answer_tokens(answer: str) -> list[str]:
    words = answer.split(" ")
    return [word if index == 0 else f" {word}" for index, word in enumerate(words)]


def sse_event(event_type: str, data) -> str:
    return f"data: {json.dumps({'type': event_type, 'data': data}, separators=(',', ':'))}\n\n"
