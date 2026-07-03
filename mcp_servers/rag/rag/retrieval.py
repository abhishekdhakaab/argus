from __future__ import annotations

import re
import time
from uuid import UUID

import structlog
from rank_bm25 import BM25Okapi
from sqlalchemy import text

from rag.store import create_engine_once, search_dense

logger = structlog.get_logger()
TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")

# A chunk-count check avoids rebuilding each tenant's BM25 index on every query.
# This trades a small per-tenant memory cache for one lightweight DB round trip.
_bm25_cache: dict[str, tuple[int, BM25Okapi, list[dict]]] = {}


def tokenize(text_value: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text_value)]


def search_sparse(query: str, tenant_id: str, top_k: int = 20) -> list[dict[str, object]]:
    if not query.strip():
        raise ValueError("Cannot search with an empty query.")
    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    parsed_tenant_id = UUID(tenant_id)
    started_at = time.perf_counter()

    try:
        with create_engine_once().connect() as connection:
            chunk_count: int = connection.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE tenant_id = :tenant_id"),
                {"tenant_id": parsed_tenant_id},
            ).scalar_one()
    except Exception:
        logger.exception("sparse_count_failed", tenant_id=tenant_id, query_len=len(query))
        raise

    if chunk_count == 0:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "sparse_search_complete",
            tenant_id=tenant_id,
            query_len=len(query),
            candidate_count=0,
            result_count=0,
            top_score=0,
            duration_ms=elapsed_ms,
        )
        return []

    cached = _bm25_cache.get(tenant_id)
    if cached is not None and cached[0] == chunk_count:
        bm25, documents = cached[1], cached[2]
    else:
        try:
            with create_engine_once().connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT id::text AS id, content, source, page
                        FROM document_chunks
                        WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": parsed_tenant_id},
                ).mappings()
                documents = [dict(row) for row in rows]
        except Exception:
            logger.exception(
                "sparse_document_load_failed",
                tenant_id=tenant_id,
                query_len=len(query),
            )
            raise

        corpus_tokens = [tokenize(str(doc["content"])) for doc in documents]
        bm25 = BM25Okapi(corpus_tokens)
        _bm25_cache[tenant_id] = (chunk_count, bm25, documents)
        logger.info("bm25_index_built", tenant_id=tenant_id, chunk_count=chunk_count)

    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)

    ranked_indexes = sorted(range(len(documents)), key=lambda index: scores[index], reverse=True)
    results: list[dict[str, object]] = []
    for index in ranked_indexes[:top_k]:
        result = dict(documents[index])
        result["score"] = float(scores[index])
        results.append(result)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "sparse_search_complete",
        tenant_id=tenant_id,
        query_len=len(query),
        candidate_count=chunk_count,
        result_count=len(results),
        top_score=round(float(results[0]["score"]), 4) if results else 0,
        duration_ms=elapsed_ms,
    )
    return results


def search_hybrid(query: str, tenant_id: str, top_k: int = 5) -> list[dict[str, object]]:
    results, _ = search_hybrid_with_metrics(query, tenant_id, top_k)
    return results


def search_hybrid_with_metrics(
    query: str,
    tenant_id: str,
    top_k: int = 5,
) -> tuple[list[dict[str, object]], dict[str, float | int]]:
    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    started_at = time.perf_counter()
    dense_results = search_dense(query, tenant_id, top_k=20)
    sparse_results = search_sparse(query, tenant_id, top_k=20)
    fused_results = reciprocal_rank_fusion([dense_results, sparse_results])[:top_k]

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "hybrid_search_complete",
        tenant_id=tenant_id,
        query_len=len(query),
        dense_count=len(dense_results),
        sparse_count=len(sparse_results),
        final_result_count=len(fused_results),
        top_score=round(float(fused_results[0]["score"]), 4) if fused_results else 0,
        duration_ms=elapsed_ms,
    )
    metrics: dict[str, float | int] = {
        "dense_count": len(dense_results),
        "sparse_count": len(sparse_results),
        "final_result_count": len(fused_results),
        "retrieval_total_ms": elapsed_ms,
    }
    return fused_results, metrics


def reciprocal_rank_fusion(
    ranked_result_sets: list[list[dict[str, object]]],
    rank_constant: int = 60,
) -> list[dict[str, object]]:
    fused_by_id: dict[str, dict[str, object]] = {}

    for result_set in ranked_result_sets:
        for rank, result in enumerate(result_set, start=1):
            result_id = str(result["id"])
            if result_id not in fused_by_id:
                fused_result = dict(result)
                fused_result["score"] = 0.0
                fused_by_id[result_id] = fused_result
            fused_by_id[result_id]["score"] = float(fused_by_id[result_id]["score"]) + (
                1.0 / (rank_constant + rank)
            )

    return sorted(
        fused_by_id.values(),
        key=lambda result: float(result["score"]),
        reverse=True,
    )
