from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from rag.retrieval import search_hybrid

ALPHA_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def main() -> None:
    results = search_hybrid("cloud spending Q3", ALPHA_TENANT_ID, top_k=3)
    if not results:
        raise ValueError("Expected hybrid search to return results.")
    if "Cloud spending increased 34%" not in str(results[0]["content"]):
        raise ValueError(f"Expected cloud spend chunk in rank 1, got: {results[0]['content']}")

    for result in results:
        print(f"  rrf_score={float(result['score']):.4f} - {str(result['content'])[:60]}")


if __name__ == "__main__":
    main()
