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
    with request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode())


def post_query(url: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            return json.loads(response.read().decode())

        answer_parts: list[str] = []
        done_event: dict[str, Any] | None = None
        buffer = ""
        for raw_line in response:
            buffer += raw_line.decode()
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                if not raw_event.startswith("data: "):
                    continue
                event = json.loads(raw_event.removeprefix("data: "))
                if event["type"] == "token":
                    answer_parts.append(event["data"])
                if event["type"] == "done":
                    done_event = event["data"]

        if done_event is None:
            raise RuntimeError("Query stream ended without a done event.")
        return {
            "run_id": done_event["run_id"],
            "answer": "".join(answer_parts),
            "status": "complete",
        }


async def stored_run(run_id: str) -> asyncpg.Record:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        row = await connection.fetchrow(
            """
            SELECT
                id::text AS id,
                answer,
                input_tokens,
                output_tokens,
                cost_usd::float AS cost_usd,
                latency_ms,
                tools_used,
                plan
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
                "The cloud budget policy sets the Q3 cloud budget target at $130,000. "
                "Any Q3 cloud spend above budget requires finance review, with AWS compute "
                "called out as the first area to inspect."
            ),
            "source": "cloud-budget-policy.pdf",
            "tenant_id": TENANT_ID,
        },
    )
    print("Ingest:", ingest_response)

    token_response = post_json(
        f"{GATEWAY_URL}/api/v1/auth/token",
        {"username": "tenant-alpha", "password": os.environ["DEV_AUTH_PASSWORD"]},
    )
    query_response = post_query(
        f"{GATEWAY_URL}/api/v1/query",
        {"query": "compare our cloud budget policy from the docs with actual Q3 spending numbers"},
        token_response["access_token"],
    )
    print("Query:", query_response)

    row = await stored_run(query_response["run_id"])
    print(
        "Stored:",
        {
            "id": row["id"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cost_usd": row["cost_usd"],
            "latency_ms": row["latency_ms"],
            "tools_used": row["tools_used"],
            "plan": row["plan"],
        },
    )

    answer = query_response["answer"].lower()
    tools_used = row["tools_used"]
    if query_response["status"] != "complete":
        raise SystemExit(f"Expected complete status, got {query_response}")
    if "budget" not in answer or "130" not in answer:
        raise SystemExit(f"Expected document budget policy in answer, got {query_response['answer']}")
    if "142000" not in answer and "142,000" not in answer:
        raise SystemExit(f"Expected SQL actual spend in answer, got {query_response['answer']}")
    if len(tools_used) < 2 or "search_documents" not in tools_used or "query_analytics" not in tools_used:
        raise SystemExit(f"Expected docs and SQL tools, got {dict(row)}")
    if row["input_tokens"] <= 0 or row["output_tokens"] <= 0 or row["cost_usd"] <= 0:
        raise SystemExit(f"Expected populated token usage, got {dict(row)}")


if __name__ == "__main__":
    asyncio.run(main())
