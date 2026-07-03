from __future__ import annotations

import time

import structlog
from sentence_transformers import CrossEncoder

from rag.config import RERANKER_MODEL_NAME
from rag.retrieval import search_hybrid_with_metrics

logger = structlog.get_logger()


def load_reranker() -> CrossEncoder:
    started_at = time.perf_counter()
    try:
        model = CrossEncoder(RERANKER_MODEL_NAME)
    except Exception:
        logger.exception("reranker_model_load_failed", model_name=RERANKER_MODEL_NAME)
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("reranker_model_loaded", model_name=RERANKER_MODEL_NAME, duration_ms=elapsed_ms)
    return model


reranker_model = load_reranker()


def rerank(query: str, candidates: list[dict[str, object]], top_k: int = 5) -> list[dict[str, object]]:
    if not query.strip():
        raise ValueError("Cannot rerank with an empty query.")
    if top_k <= 0:
        raise ValueError("top_k must be positive.")
    if not candidates:
        logger.info(
            "rerank_complete",
            query_len=len(query),
            rerank_input_count=0,
            final_result_count=0,
            top_score=0,
            rerank_ms=0,
        )
        return []

    started_at = time.perf_counter()
    pairs = [(query, str(candidate["content"])) for candidate in candidates]

    try:
        scores = reranker_model.predict(pairs)
    except Exception:
        logger.exception(
            "rerank_failed",
            query_len=len(query),
            rerank_input_count=len(candidates),
        )
        raise

    scored_candidates: list[dict[str, object]] = []
    for candidate, score in zip(candidates, scores, strict=True):
        scored_candidate = dict(candidate)
        scored_candidate["score"] = float(score)
        scored_candidates.append(scored_candidate)

    scored_candidates.sort(key=lambda candidate: float(candidate["score"]), reverse=True)
    results = scored_candidates[:top_k]
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "rerank_complete",
        model_name=RERANKER_MODEL_NAME,
        query_len=len(query),
        rerank_input_count=len(candidates),
        final_result_count=len(results),
        top_score=round(float(results[0]["score"]), 4) if results else 0,
        rerank_ms=elapsed_ms,
    )
    return results


def search_and_rerank(
    query: str,
    tenant_id: str,
    top_k: int = 5,
) -> tuple[list[dict[str, object]], dict[str, float | int]]:
    started_at = time.perf_counter()
    candidates, retrieval_metrics = search_hybrid_with_metrics(query, tenant_id, top_k=20)
    rerank_started_at = time.perf_counter()
    results = rerank(query, candidates, top_k=top_k)
    rerank_ms = round((time.perf_counter() - rerank_started_at) * 1000, 2)
    total_ms = round((time.perf_counter() - started_at) * 1000, 2)

    metrics = {
        **retrieval_metrics,
        "rerank_input_count": len(candidates),
        "final_result_count": len(results),
        "rerank_ms": rerank_ms,
        "retrieval_total_ms": total_ms,
    }
    logger.info(
        "search_and_rerank_complete",
        tenant_id=tenant_id,
        query_len=len(query),
        dense_count=metrics["dense_count"],
        sparse_count=metrics["sparse_count"],
        rerank_input_count=metrics["rerank_input_count"],
        final_result_count=metrics["final_result_count"],
        retrieval_total_ms=metrics["retrieval_total_ms"],
        rerank_ms=metrics["rerank_ms"],
    )
    return results, metrics
