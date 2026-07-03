from __future__ import annotations

import json
import os
import time
from contextlib import nullcontext
from typing import Any

import httpx
import structlog

try:
    from opentelemetry import trace as _otel
    _tracer = _otel.get_tracer("argus.synthesis")
except ImportError:
    _tracer = None  # type: ignore[assignment]

from agent.config import (
    DEFAULT_SYNTHESIS_MODEL,
    INPUT_COST_PER_1K,
    OPENAI_CHAT_COMPLETIONS_URL,
    OUTPUT_COST_PER_1K,
)
from agent.state import AgentState

logger = structlog.get_logger()


async def synthesis_node(state: AgentState) -> dict[str, Any]:
    span_ctx = _tracer.start_as_current_span("langgraph.synthesis") if _tracer else nullcontext()
    with span_ctx as span:
        started_at = time.perf_counter()
        all_context = state["doc_context"] + state["sql_context"] + state["api_context"]
        prompt = build_synthesis_prompt(state["query"], all_context)

        if span:
            span.set_attribute("tenant_id", state["tenant_id"])
            span.set_attribute("run_id", state["run_id"])
            span.set_attribute("context_chunks", len(all_context))

        if os.getenv("OPENAI_API_KEY"):
            try:
                answer, usage = await stream_openai_answer(prompt)
                synthesis_mode = "openai"
            except Exception:
                logger.exception("synthesis_llm_failed_using_fallback", run_id=state["run_id"])
                answer, usage = synthesize_from_context(prompt, all_context)
                synthesis_mode = "extractive_fallback"
        else:
            logger.warning(
                "synthesis_llm_unavailable_using_fallback",
                reason="OPENAI_API_KEY missing",
                run_id=state["run_id"],
            )
            answer, usage = synthesize_from_context(prompt, all_context)
            synthesis_mode = "extractive_fallback"

        usage["cost_usd"] = calculate_cost(usage["input_tokens"], usage["output_tokens"])
        token_usage = {**state["token_usage"], **usage}

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        if span:
            span.set_attribute("input_tokens", usage["input_tokens"])
            span.set_attribute("output_tokens", usage["output_tokens"])
            span.set_attribute("cost_usd", usage["cost_usd"])
            span.set_attribute("synthesis_mode", synthesis_mode)
            span.set_attribute("duration_ms", elapsed_ms)

        logger.info(
            "synthesis_complete",
            run_id=state["run_id"],
            tenant_id=state["tenant_id"],
            synthesis_mode=synthesis_mode,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=usage["cost_usd"],
            answer_len=len(answer),
            context_chunks=len(all_context),
            duration_ms=elapsed_ms,
        )
        return {"answer": answer, "token_usage": token_usage}


def build_synthesis_prompt(query: str, context: list[str]) -> str:
    context_text = "\n\n".join(f"- {item}" for item in context)
    return f"""
Answer the user's enterprise intelligence question using only the provided context.
If the context is thin, say what is known and avoid inventing details.

Question:
{query}

Context:
{context_text}
""".strip()


async def stream_openai_answer(prompt: str) -> tuple[str, dict[str, int]]:
    started_at = time.perf_counter()
    chunks: list[str] = []
    usage: dict[str, int] | None = None
    payload = {
        "model": DEFAULT_SYNTHESIS_MODEL,
        "stream": True,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "You are Argus. Give concise, grounded answers for enterprise users.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = line.removeprefix("data: ").strip()
                    if event == "[DONE]":
                        break
                    parsed = json.loads(event)
                    if parsed.get("usage"):
                        usage = {
                            "input_tokens": int(parsed["usage"].get("prompt_tokens", 0)),
                            "output_tokens": int(parsed["usage"].get("completion_tokens", 0)),
                        }
                    choices = parsed.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if delta.get("content"):
                        chunks.append(delta["content"])
    except Exception:
        logger.exception("synthesis_llm_stream_failed", prompt_len=len(prompt))
        raise

    answer = "".join(chunks).strip()
    if not answer:
        raise ValueError("OpenAI returned an empty synthesis answer.")

    if usage is None or usage["input_tokens"] == 0 or usage["output_tokens"] == 0:
        usage = {
            "input_tokens": estimate_tokens(prompt),
            "output_tokens": estimate_tokens(answer),
        }

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "synthesis_llm_stream_complete",
        model=DEFAULT_SYNTHESIS_MODEL,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        duration_ms=elapsed_ms,
    )
    return answer, usage


def synthesize_from_context(prompt: str, context: list[str]) -> tuple[str, dict[str, int]]:
    if not context:
        answer = "I did not find supporting document context for this question."
    else:
        core_facts = [clean_context_entry(item) for item in select_context_for_fallback(context)]
        answer = "Based on the retrieved documents, " + " ".join(core_facts)

    usage = {
        "input_tokens": estimate_tokens(prompt),
        "output_tokens": estimate_tokens(answer),
    }
    return answer, usage


def clean_context_entry(entry: str) -> str:
    if "] " in entry:
        return entry.split("] ", 1)[1].strip()
    return entry.strip()


def select_context_for_fallback(context: list[str]) -> list[str]:
    sql_entries = [item for item in context if item.startswith("[query_analytics")]
    api_entries = [item for item in context if item.startswith("[fetch_external_data")]
    document_entries = [
        item
        for item in context
        if not item.startswith("[query_analytics") and not item.startswith("[fetch_external_data")
    ]
    selected = document_entries[:3] + sql_entries[:2] + api_entries[:1]
    return selected or context[:6]


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.33))


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1000) * INPUT_COST_PER_1K
        + (output_tokens / 1000) * OUTPUT_COST_PER_1K,
        8,
    )
