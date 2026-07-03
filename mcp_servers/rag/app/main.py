from __future__ import annotations

import logging
import time

import structlog
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from rag.chunker import chunk_text
from rag.reranker import search_and_rerank
from rag.store import ingest_chunks

logging.basicConfig(format="%(message)s", level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

app = FastAPI(title="Argus RAG MCP Server", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class SearchDocumentsRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    tenant_id: str = Field(min_length=36, max_length=36)


class IngestDocumentRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    tenant_id: str = Field(min_length=36, max_length=36)


class IngestDocumentResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    chunks_inserted: int


class DocumentSearchResult(BaseModel):
    model_config = ConfigDict(strict=True)

    text: str
    source: str | None
    page: int | None
    score: float


class SearchDocumentsResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    results: list[DocumentSearchResult]


@app.post("/tools/ingest_document", response_model=IngestDocumentResponse)
def ingest_document(payload: IngestDocumentRequest) -> IngestDocumentResponse:
    started_at = time.perf_counter()

    try:
        chunks = chunk_text(payload.text)
        if not chunks and payload.text.strip():
            chunks = [payload.text.strip()]
        chunks_inserted = ingest_chunks(chunks, payload.source, payload.tenant_id)
    except Exception as exc:
        logger.exception(
            "mcp_ingest_failed",
            tool="ingest_document",
            tenant_id=payload.tenant_id,
            source=payload.source,
            input_chars=len(payload.text),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingest failed",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "mcp_ingest_complete",
        tool="ingest_document",
        tenant_id=payload.tenant_id,
        source=payload.source,
        input_chars=len(payload.text),
        chunks_inserted=chunks_inserted,
        duration_ms=elapsed_ms,
    )
    return IngestDocumentResponse(chunks_inserted=chunks_inserted)


@app.post("/tools/search_documents", response_model=SearchDocumentsResponse)
def search_documents(payload: SearchDocumentsRequest) -> SearchDocumentsResponse:
    started_at = time.perf_counter()

    try:
        ranked_results, search_metrics = search_and_rerank(
            payload.query,
            payload.tenant_id,
            payload.top_k,
        )
    except Exception as exc:
        logger.exception(
            "mcp_search_failed",
            tool="search_documents",
            tenant_id=payload.tenant_id,
            query_len=len(payload.query),
            top_k=payload.top_k,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document search failed",
        ) from exc

    results = [
        DocumentSearchResult(
            text=str(result["content"]),
            source=result["source"],
            page=result["page"],
            score=float(result["score"]),
        )
        for result in ranked_results
    ]

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "mcp_search_complete",
        tool="search_documents",
        tenant_id=payload.tenant_id,
        query_len=len(payload.query),
        dense_count=search_metrics["dense_count"],
        sparse_count=search_metrics["sparse_count"],
        rerank_input_count=search_metrics["rerank_input_count"],
        result_count=len(results),
        final_result_count=len(results),
        top_score=round(results[0].score, 4) if results else 0,
        retrieval_total_ms=search_metrics["retrieval_total_ms"],
        rerank_ms=search_metrics["rerank_ms"],
        duration_ms=elapsed_ms,
    )
    return SearchDocumentsResponse(results=results)
