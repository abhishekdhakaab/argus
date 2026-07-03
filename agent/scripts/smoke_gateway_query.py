from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import request

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TENANT_ID = "00000000-0000-0000-0000-000000000001"
GATEWAY_URL = "http://127.0.0.1:8080"
RAG_URL = "http://127.0.0.1:8081"
DATABASE_URL = os.environ["DB_DSN"]


def post_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


async def latest_query_run(run_id: str) -> asyncpg.Record:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        row = await connection.fetchrow(
            """
            SELECT
                id::text AS id,
                LEFT(answer, 140) AS answer_preview,
                input_tokens,
                output_tokens,
                cost_usd::float AS cost_usd,
                latency_ms,
                tools_used
            FROM query_runs
            WHERE tenant_id = $1
              AND id = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            TENANT_ID,
            run_id,
        )
    finally:
        await connection.close()

    if row is None:
        raise RuntimeError(f"Could not find query_run {run_id} for tenant {TENANT_ID}.")
    return row


async def main() -> None:
    ingest_response = post_json(
        f"{RAG_URL}/tools/ingest_document",
        {
            "text": (
                "Cloud spending in Q3 was $142,000, up 34% from Q2. "
                "The increase was driven by AWS compute and analytics batch jobs."
            ),
            "source": "q3-full-stack-smoke.pdf",
            "tenant_id": TENANT_ID,
        },
    )
    print("Ingest:", ingest_response)

    token_response = post_json(
        f"{GATEWAY_URL}/api/v1/auth/token",
        {"username": "tenant-alpha", "password": os.environ["DEV_AUTH_PASSWORD"]},
    )
    token = token_response["access_token"]

    query_response = post_json(
        f"{GATEWAY_URL}/api/v1/query",
        {"query": "what was the exact cloud spending dollar amount in Q3?"},
        token=token,
    )
    print("Query:", query_response)

    row = await latest_query_run(query_response["run_id"])
    print("Stored:", dict(row))

    if query_response["status"] != "complete":
        raise SystemExit(f"Expected complete status, got {query_response}")
    if "142" not in query_response["answer"]:
        raise SystemExit(f"Expected answer to reference $142,000, got {query_response['answer']}")
    if row["input_tokens"] is None or row["output_tokens"] is None or row["cost_usd"] is None:
        raise SystemExit(f"Expected populated token and cost fields, got {dict(row)}")
    if row["cost_usd"] <= 0 or row["latency_ms"] is None:
        raise SystemExit(f"Expected positive cost and latency, got {dict(row)}")
    if "search_documents" not in row["tools_used"]:
        raise SystemExit(f"Expected search_documents in tools_used, got {dict(row)}")


if __name__ == "__main__":
    asyncio.run(main())
