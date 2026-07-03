from __future__ import annotations

import time
from typing import Any, Callable, Literal

import httpx
import structlog

from agent.state import AgentState

logger = structlog.get_logger()

ToolName = Literal["search_documents", "query_analytics", "fetch_external_data"]
ContextField = Literal["doc_context", "sql_context", "api_context"]
TOOL_CONTEXT_FIELDS: dict[str, ContextField] = {
    "search_documents": "doc_context",
    "query_analytics": "sql_context",
    "fetch_external_data": "api_context",
}
DEFAULT_TOP_K = 5
MCP_TIMEOUT_SECONDS = 8.0


def create_retrieval_node(mcp_url: str, tool_name: ToolName) -> Callable[[AgentState], Any]:
    context_field = TOOL_CONTEXT_FIELDS[tool_name]
    tool_url = f"{mcp_url.rstrip('/')}/tools/{tool_name}"

    async def retrieval_node(state: AgentState) -> dict[str, list[str]]:
        started_at = time.perf_counter()
        plan_items = planned_queries(state, tool_name)

        if not plan_items:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "retrieval_skipped",
                run_id=state["run_id"],
                tenant_id=state["tenant_id"],
                tool=tool_name,
                reason="tool_not_selected",
                duration_ms=elapsed_ms,
            )
            return {context_field: []}

        try:
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
                context_entries: list[str] = []
                for plan_item in plan_items:
                    payload = build_payload(tool_name, plan_item["sub_query"], state["tenant_id"])
                    response = await client.post(tool_url, json=payload)
                    response.raise_for_status()
                    context_entries.extend(format_tool_response(tool_name, response.json()))
        except httpx.TimeoutException:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.warning(
                "retrieval_timeout",
                run_id=state["run_id"],
                tenant_id=state["tenant_id"],
                tool=tool_name,
                plan_matches=len(plan_items),
                timeout_seconds=MCP_TIMEOUT_SECONDS,
                duration_ms=elapsed_ms,
            )
            return {context_field: []}
        except Exception:
            logger.exception(
                "retrieval_failed",
                run_id=state["run_id"],
                tenant_id=state["tenant_id"],
                tool=tool_name,
                plan_matches=len(plan_items),
            )
            raise

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "retrieval_complete",
            run_id=state["run_id"],
            tenant_id=state["tenant_id"],
            tool=tool_name,
            plan_matches=len(plan_items),
            result_count=len(context_entries),
            context_chars=sum(len(entry) for entry in context_entries),
            duration_ms=elapsed_ms,
        )
        return {context_field: context_entries}

    return retrieval_node


def matching_plan_items(plan: list[dict], tool_name: str) -> list[dict]:
    return [item for item in plan if item.get("tool") == tool_name and item.get("sub_query")]


def planned_queries(state: AgentState, tool_name: str) -> list[dict]:
    active_sub_query = state.get("active_sub_query")
    if active_sub_query:
        return [{"tool": tool_name, "sub_query": active_sub_query}]
    return matching_plan_items(state["plan"], tool_name)


def build_payload(tool_name: str, sub_query: str, tenant_id: str) -> dict[str, Any]:
    if tool_name == "search_documents":
        return {"query": sub_query, "top_k": DEFAULT_TOP_K, "tenant_id": tenant_id}
    if tool_name == "query_analytics":
        return {"question": sub_query, "tenant_id": tenant_id}
    if tool_name == "fetch_external_data":
        return {"resource": sub_query, "filters": {}, "tenant_id": tenant_id}
    raise ValueError(f"Unsupported retrieval tool: {tool_name}")


def format_tool_response(tool_name: str, response: dict[str, Any]) -> list[str]:
    if tool_name == "search_documents":
        return format_document_results(response.get("results", []))
    if tool_name == "query_analytics":
        return format_sql_response(response)
    if tool_name == "fetch_external_data":
        return format_api_response(response)
    raise ValueError(f"Unsupported retrieval tool: {tool_name}")


def format_document_results(results: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for result in results:
        source = result.get("source") or "unknown source"
        page = result.get("page")
        score = result.get("score")
        page_label = f", page {page}" if page is not None else ""
        score_label = f", score {float(score):.3f}" if score is not None else ""
        entries.append(f"[{source}{page_label}{score_label}] {result.get('text', '')}".strip())
    return entries


def format_sql_response(response: dict[str, Any]) -> list[str]:
    rows = response.get("rows", [])
    row_text = "; ".join(format_row(row) for row in rows)
    return [
        (
            f"[query_analytics, rows {response.get('row_count', len(rows))}] "
            f"SQL: {response.get('sql', '')}. Results: {row_text}"
        ).strip()
    ]


def format_api_response(response: dict[str, Any]) -> list[str]:
    rows = response.get("data", [])
    row_text = "; ".join(format_row(row) for row in rows)
    return [
        (
            f"[fetch_external_data from {response.get('source', 'legacy API')}, "
            f"fetched_at {response.get('fetched_at', 'unknown')}] Results: {row_text}"
        ).strip()
    ]


def format_row(row: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in row.items())
