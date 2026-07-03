from __future__ import annotations

import os
import time
from uuid import UUID

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from rag.embedder import embed_batch

logger = structlog.get_logger()
engine: Engine | None = None


def database_url() -> str:
    return os.environ["DATABASE_URL"]


def create_engine_once() -> Engine:
    global engine

    if engine is not None:
        return engine

    started_at = time.perf_counter()
    engine = create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=10)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("rag_database_engine_created", duration_ms=elapsed_ms)
    return engine


def ingest_chunks(chunks: list[str], source: str, tenant_id: str) -> int:
    if not chunks:
        logger.info("ingest_complete", tenant_id=tenant_id, source=source, chunks=0, duration_ms=0)
        return 0
    if any(not chunk.strip() for chunk in chunks):
        raise ValueError("Cannot ingest empty document chunks.")

    parsed_tenant_id = UUID(tenant_id)
    started_at = time.perf_counter()
    embedding_started_at = time.perf_counter()

    try:
        embeddings = embed_batch(chunks)
    except Exception:
        logger.exception(
            "chunk_embedding_failed",
            tenant_id=str(parsed_tenant_id),
            source=source,
            chunks=len(chunks),
        )
        raise

    embedding_ms = round((time.perf_counter() - embedding_started_at) * 1000, 2)
    rows = [
        {
            "tenant_id": parsed_tenant_id,
            "source": source,
            "page": None,
            "content": chunk,
            "embedding": _format_vector(embedding),
        }
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]

    insert_started_at = time.perf_counter()
    try:
        with create_engine_once().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO document_chunks (tenant_id, source, page, content, embedding)
                    VALUES (:tenant_id, :source, :page, :content, :embedding)
                    """
                ),
                rows,
            )
    except Exception:
        logger.exception(
            "chunk_insert_failed",
            tenant_id=str(parsed_tenant_id),
            source=source,
            chunks=len(chunks),
        )
        raise

    insert_ms = round((time.perf_counter() - insert_started_at) * 1000, 2)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "ingest_complete",
        tenant_id=str(parsed_tenant_id),
        source=source,
        chunks=len(chunks),
        embedding_ms=embedding_ms,
        embedding_ms_per_chunk=round(embedding_ms / len(chunks), 2),
        insert_ms=insert_ms,
        duration_ms=elapsed_ms,
    )
    return len(chunks)


def search_dense(query: str, tenant_id: str, top_k: int = 20) -> list[dict[str, object]]:
    if not query.strip():
        raise ValueError("Cannot search with an empty query.")
    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    parsed_tenant_id = UUID(tenant_id)
    started_at = time.perf_counter()
    embedding_started_at = time.perf_counter()

    try:
        query_embedding = embed_batch([query])[0]
    except Exception:
        logger.exception(
            "query_embedding_failed",
            tenant_id=str(parsed_tenant_id),
            query_len=len(query),
        )
        raise

    embedding_ms = round((time.perf_counter() - embedding_started_at) * 1000, 2)
    db_started_at = time.perf_counter()

    try:
        with create_engine_once().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id::text AS id,
                        content,
                        source,
                        page,
                        1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
                    FROM document_chunks
                    WHERE tenant_id = :tenant_id
                    ORDER BY embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :top_k
                    """
                ),
                {
                    "query_embedding": _format_vector(query_embedding),
                    "tenant_id": parsed_tenant_id,
                    "top_k": top_k,
                },
            ).mappings()
            results = [dict(row) for row in rows]
    except Exception:
        logger.exception(
            "dense_search_failed",
            tenant_id=str(parsed_tenant_id),
            query_len=len(query),
            top_k=top_k,
        )
        raise

    db_ms = round((time.perf_counter() - db_started_at) * 1000, 2)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "dense_search_complete",
        tenant_id=str(parsed_tenant_id),
        query_len=len(query),
        top_k=top_k,
        result_count=len(results),
        top_score=round(float(results[0]["score"]), 4) if results else 0,
        embedding_ms=embedding_ms,
        db_ms=db_ms,
        duration_ms=elapsed_ms,
    )
    return results


def _format_vector(vector: list[float]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"
