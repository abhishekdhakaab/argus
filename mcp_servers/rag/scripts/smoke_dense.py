from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from rag.store import search_dense

ALPHA_TENANT_ID = "00000000-0000-0000-0000-000000000001"
BETA_TENANT_ID = "00000000-0000-0000-0000-000000000002"


def main() -> None:
    results = search_dense("cloud spending", ALPHA_TENANT_ID, top_k=5)
    if not results:
        raise ValueError("Expected alpha dense search to return document chunks.")
    if not any("Cloud spending increased 34%" in str(result["content"]) for result in results):
        raise ValueError("Expected the Q3 cloud spending chunk to appear in alpha results.")
    if float(results[0]["score"]) <= 0.5:
        raise ValueError(f"Expected top score > 0.5, got {results[0]['score']}.")

    print(f"Results: {len(results)}")
    for result in results:
        print(f"  score={float(result['score']):.3f} - {str(result['content'])[:60]}")

    beta_results = search_dense("cloud spending", BETA_TENANT_ID, top_k=5)
    if beta_results:
        raise ValueError(f"Expected beta results to be empty, got {len(beta_results)}.")
    print(f"Beta results: {len(beta_results)}")


if __name__ == "__main__":
    main()
