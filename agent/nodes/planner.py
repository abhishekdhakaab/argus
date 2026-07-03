from __future__ import annotations

import json
import os
import time
from contextlib import nullcontext
from json import JSONDecodeError
from typing import Literal

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.config import OPENAI_CHAT_COMPLETIONS_URL
from agent.state import AgentState

try:
    from opentelemetry import trace as _otel
    _tracer = _otel.get_tracer("argus.planner")
except ImportError:
    _tracer = None  # type: ignore[assignment]

logger = structlog.get_logger()

ToolName = Literal["search_documents", "query_analytics", "fetch_external_data"]
DEFAULT_PLANNER_MODEL = "gpt-4o-mini"


_PRIORITY_MAP = {"high": 1, "medium": 2, "low": 3, "critical": 1}


def _coerce_priority(v: object) -> int:
    if isinstance(v, str):
        return _PRIORITY_MAP.get(v.lower(), 1)
    try:
        return max(1, min(3, int(float(v))))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


class PlanItem(BaseModel):
    model_config = ConfigDict(strict=False)

    tool: ToolName
    sub_query: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1, le=3)

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> "PlanItem":
        if isinstance(obj, dict) and "priority" in obj:
            obj = {**obj, "priority": _coerce_priority(obj["priority"])}
        return super().model_validate(obj, **kwargs)


class PlannerOutput(BaseModel):
    model_config = ConfigDict(strict=False)

    plan: list[PlanItem]


async def planner_node(state: AgentState) -> dict[str, list[dict]]:
    span_ctx = _tracer.start_as_current_span("langgraph.planner") if _tracer else nullcontext()
    with span_ctx as span:
        started_at = time.perf_counter()
        query = state["query"]

        if span:
            span.set_attribute("tenant_id", state["tenant_id"])
            span.set_attribute("run_id", state["run_id"])
            span.set_attribute("query_len", len(query))

        if os.getenv("OPENAI_API_KEY"):
            plan = await plan_with_openai(query)
            planner_mode = "openai"
        else:
            logger.warning(
                "planner_llm_unavailable_using_heuristic",
                reason="OPENAI_API_KEY missing",
                run_id=state["run_id"],
            )
            plan = heuristic_plan(query)
            planner_mode = "heuristic"

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        if span:
            span.set_attribute("plan_length", len(plan))
            span.set_attribute("planner_mode", planner_mode)
            span.set_attribute("duration_ms", elapsed_ms)

        logger.info(
            "planner_complete",
            run_id=state["run_id"],
            tenant_id=state["tenant_id"],
            planner_mode=planner_mode,
            query_len=len(query),
            plan_length=len(plan),
            tools_selected=[item["tool"] for item in plan],
            duration_ms=elapsed_ms,
        )
        return {"plan": plan}


async def plan_with_openai(query: str) -> list[dict]:
    prompt = build_planner_prompt(query)
    payload = {
        "model": os.getenv("PLANNER_MODEL", DEFAULT_PLANNER_MODEL),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the Argus planner. Decompose enterprise intelligence "
                    "questions into tool calls. Respond in JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    started_at = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            raw_content = response.json()["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("planner_llm_call_failed", query_len=len(query))
        return fallback_all_tools(query)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("planner_llm_call_complete", query_len=len(query), duration_ms=elapsed_ms)
    return parse_plan(raw_content, query)


def build_planner_prompt(query: str) -> str:
    return f"""
Analyze this user query and choose the minimum required tools.

Available tools:
- search_documents: internal policy docs, reports, uploaded files, source text
- query_analytics: spend, counts, metrics, tables, numeric analytics
- fetch_external_data: legacy API records, external system status, vendor resources

Return JSON only in this exact shape:
{{"plan":[{{"tool":"search_documents","sub_query":"...","priority":1}}]}}

User query: {query}
""".strip()


def parse_plan(raw_content: str, query: str) -> list[dict]:
    try:
        parsed = json.loads(strip_json_fence(raw_content))
        # Local models occasionally omit the expected top-level object.
        if isinstance(parsed, list):
            parsed = {"plan": parsed}
        planner_output = PlannerOutput.model_validate(parsed)
    except (JSONDecodeError, ValidationError) as exc:
        logger.exception("planner_json_parse_failed", raw_response=raw_content)
        return fallback_all_tools(query)

    if not planner_output.plan:
        logger.warning("planner_returned_empty_plan", raw_response=raw_content)
        return fallback_all_tools(query)

    return [item.model_dump() for item in planner_output.plan]


def strip_json_fence(raw_content: str) -> str:
    stripped = raw_content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped


def heuristic_plan(query: str) -> list[dict]:
    normalized = query.lower()
    plan: list[PlanItem] = []

    if any(word in normalized for word in ["document", "policy", "report", "cloud", "q3"]):
        plan.append(PlanItem(tool="search_documents", sub_query=query, priority=1))

    if any(word in normalized for word in ["spend", "spending", "cost", "revenue", "count", "metric"]):
        plan.append(PlanItem(tool="query_analytics", sub_query=query, priority=2))

    if any(word in normalized for word in ["legacy", "external", "vendor", "status", "api"]):
        plan.append(PlanItem(tool="fetch_external_data", sub_query=query, priority=3))

    if not plan:
        plan.append(PlanItem(tool="search_documents", sub_query=query, priority=1))

    return [item.model_dump() for item in plan]


def fallback_all_tools(query: str) -> list[dict]:
    return [
        PlanItem(tool="search_documents", sub_query=query, priority=1).model_dump(),
        PlanItem(tool="query_analytics", sub_query=query, priority=2).model_dump(),
        PlanItem(tool="fetch_external_data", sub_query=query, priority=3).model_dump(),
    ]
