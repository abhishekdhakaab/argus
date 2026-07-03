from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from rag.config import EMBEDDING_DIMENSION
from rag.embedder import embed_text


def main() -> None:
    vector = embed_text("cloud spending in Q3")
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError(f"Wrong dimension: {len(vector)}")
    if not all(isinstance(value, float) for value in vector):
        raise ValueError("Embedding contains non-float values.")
    if all(abs(value) < 1e-12 for value in vector):
        raise ValueError("Embedding looks empty; all values are effectively zero.")

    print(f"Embedding OK. Dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")


if __name__ == "__main__":
    main()
