from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from rag.reranker import search_and_rerank
from rag.store import ingest_chunks

ALPHA_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def main() -> None:
    ingest_chunks(
        chunks=[
            "AWS compute cost Q3 was the largest cloud driver, led by analytics batch jobs.",
            "Office snack spending stayed flat in Q3 and did not affect cloud infrastructure.",
            "The document retention policy requires seven years of archive storage.",
            "Customer onboarding improved after the support team rewrote the setup checklist.",
            "Azure legacy synchronization jobs represented a smaller share of Q3 cloud spend.",
            "The sales team reviewed renewal risk for customers in the financial services segment.",
            "Google Cloud database capacity grew because ingestion jobs processed larger PDFs.",
            "The security team required tenant filters on every document chunk query.",
            "BM25 retrieval helps exact policy terms like rollback plan and cost center.",
            "The dashboard reports p95 latency, average cost, and query count by tenant.",
        ],
        source="rerank-smoke.txt",
        tenant_id=ALPHA_TENANT_ID,
    )

    results, metrics = search_and_rerank("AWS compute cost Q3", ALPHA_TENANT_ID, top_k=3)
    if not results:
        raise ValueError("Expected reranked results.")
    if "AWS compute cost Q3" not in str(results[0]["content"]):
        raise ValueError(f"Expected AWS compute cost chunk at rank 1, got: {results[0]['content']}")
    if float(results[0]["score"]) <= 5.0:
        raise ValueError(f"Expected cross-encoder score > 5.0, got {results[0]['score']}.")

    print(f"Top result: {str(results[0]['content'])[:80]}")
    print(f"Cross-encoder score: {float(results[0]['score']):.3f}")
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    main()
