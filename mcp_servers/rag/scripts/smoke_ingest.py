from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from rag.store import ingest_chunks


def main() -> None:
    count = ingest_chunks(
        chunks=[
            "Cloud spending increased 34% in Q3 driven by compute costs.",
            "AWS accounted for 60% of total cloud expenditure in the period.",
        ],
        source="q3-report.pdf",
        tenant_id="00000000-0000-0000-0000-000000000001",
    )
    if count != 2:
        raise ValueError(f"Expected to insert 2 chunks, inserted {count}.")
    print(f"Inserted {count} chunks")


if __name__ == "__main__":
    main()
