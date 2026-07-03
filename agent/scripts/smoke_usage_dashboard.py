from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib import request

import asyncpg

GATEWAY_URL = "http://127.0.0.1:8080"
DATABASE_URL = os.environ["DB_DSN"]
TENANT_ID = "00000000-0000-0000-0000-000000000001"


def post_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def get_json(url: str, token: str) -> dict[str, Any]:
    req = request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def auth_token() -> str:
    response = post_json(
        f"{GATEWAY_URL}/api/v1/auth/token",
        {"username": "tenant-alpha", "password": os.environ["DEV_AUTH_PASSWORD"]},
    )
    return response["access_token"]


def consume_sse_query(token: str, query: str) -> dict[str, Any]:
    body = json.dumps({"query": query}).encode()
    req = request.Request(
        f"{GATEWAY_URL}/api/v1/query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    done_event: dict[str, Any] | None = None
    with request.urlopen(req, timeout=60) as response:
        buffer = ""
        for raw_line in response:
            buffer += raw_line.decode()
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                if not raw_event.startswith("data: "):
                    continue
                event = json.loads(raw_event.removeprefix("data: "))
                if event["type"] == "done":
                    done_event = event["data"]

    if done_event is None:
        raise RuntimeError("SSE query finished without a done event.")
    return done_event


async def usage_from_database() -> dict[str, Any]:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        totals = await connection.fetchrow(
            """
            SELECT
                COUNT(*)::int AS queries_today,
                COALESCE(AVG(latency_ms), 0)::float AS avg_latency_ms,
                COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0)::float
                    AS p95_latency_ms,
                COALESCE(SUM(cost_usd), 0)::float AS total_cost_usd,
                COALESCE(AVG(cost_usd), 0)::float AS avg_cost_per_query
            FROM query_runs
            WHERE tenant_id = $1
              AND created_at >= date_trunc('day', NOW())
            """,
            TENANT_ID,
        )
        tools = await connection.fetch(
            """
            SELECT tool
            FROM query_runs
            CROSS JOIN LATERAL unnest(tools_used) AS tool
            WHERE tenant_id = $1
              AND created_at >= date_trunc('day', NOW())
            GROUP BY tool
            ORDER BY COUNT(*) DESC, tool ASC
            LIMIT 5
            """,
            TENANT_ID,
        )
    finally:
        await connection.close()

    return {
        "queries_today": totals["queries_today"],
        "avg_latency_ms": round(totals["avg_latency_ms"], 2),
        "p95_latency_ms": round(totals["p95_latency_ms"], 2),
        "total_cost_usd": round(totals["total_cost_usd"], 6),
        "avg_cost_per_query": round(totals["avg_cost_per_query"], 6),
        "top_tools": [row["tool"] for row in tools],
    }


async def main() -> None:
    token = auth_token()
    before = await usage_from_database()
    if before["queries_today"] < 10:
        for index in range(15):
            done = consume_sse_query(token, f"what was cloud spending in Q3? smoke {index}")
            print("Submitted:", done)

    api_usage = get_json(f"{GATEWAY_URL}/api/v1/tenants/{TENANT_ID}/usage", token)
    db_usage = await usage_from_database()
    print("API usage:", api_usage)
    print("DB usage:", db_usage)

    for key in ["queries_today", "avg_latency_ms", "p95_latency_ms", "total_cost_usd", "avg_cost_per_query"]:
        if api_usage[key] != db_usage[key]:
            raise SystemExit(f"Usage mismatch for {key}: API={api_usage[key]} DB={db_usage[key]}")
    if api_usage["top_tools"] != db_usage["top_tools"]:
        raise SystemExit(f"Top tools mismatch: API={api_usage['top_tools']} DB={db_usage['top_tools']}")


if __name__ == "__main__":
    asyncio.run(main())
