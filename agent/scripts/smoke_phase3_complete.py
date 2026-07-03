from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib import request

import asyncpg

GATEWAY_URL = "http://127.0.0.1:8080"
DATABASE_URL = os.environ["DB_DSN"]
ALPHA_TENANT_ID = "00000000-0000-0000-0000-000000000001"
BETA_TENANT_ID = "00000000-0000-0000-0000-000000000002"


def post_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode())


def token_for(username: str) -> str:
    response = post_json(
        f"{GATEWAY_URL}/api/v1/auth/token",
        {"username": username, "password": os.environ["DEV_AUTH_PASSWORD"]},
    )
    return response["access_token"]


async def stored_tools(run_id: str, tenant_id: str) -> list[str]:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        row = await connection.fetchrow(
            """
            SELECT tools_used
            FROM query_runs
            WHERE tenant_id = $1
              AND id = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            tenant_id,
            run_id,
        )
    finally:
        await connection.close()

    if row is None:
        raise RuntimeError(f"Missing query_run {run_id} for tenant {tenant_id}.")
    return list(row["tools_used"])


async def main() -> None:
    alpha_token = token_for("tenant-alpha")
    alpha_query = post_json(
        f"{GATEWAY_URL}/api/v1/query",
        {
            "query": (
                "compare our cloud budget policy from the docs with actual Q3 spending "
                "numbers and legacy vendor status"
            )
        },
        token=alpha_token,
    )
    alpha_tools = await stored_tools(alpha_query["run_id"], ALPHA_TENANT_ID)
    print("Alpha:", {"response": alpha_query, "tools_used": alpha_tools})

    alpha_answer = alpha_query["answer"].lower()
    if not {"search_documents", "query_analytics", "fetch_external_data"} <= set(alpha_tools):
        raise SystemExit(f"Expected all three tools for alpha query, got {alpha_tools}")
    if "budget" not in alpha_answer or "142000" not in alpha_answer:
        raise SystemExit(f"Expected alpha answer to include doc and SQL context, got {alpha_query['answer']}")
    if "legacy-billing" not in alpha_answer and "acmecloud" not in alpha_answer:
        raise SystemExit(f"Expected alpha answer to include external API context, got {alpha_query['answer']}")

    beta_token = token_for("tenant-beta")
    beta_query = post_json(
        f"{GATEWAY_URL}/api/v1/query",
        {"query": "what does the cloud budget policy say about Q3 and what was actual Q3 spending?"},
        token=beta_token,
    )
    beta_tools = await stored_tools(beta_query["run_id"], BETA_TENANT_ID)
    print("Beta:", {"response": beta_query, "tools_used": beta_tools})

    beta_answer = beta_query["answer"].lower()
    if "142,000" in beta_answer or "142000" in beta_answer or "130,000" in beta_answer:
        raise SystemExit(f"Tenant-beta leaked alpha context: {beta_query['answer']}")
    if "37000" not in beta_answer:
        raise SystemExit(f"Expected beta tenant SQL result only, got {beta_query['answer']}")
    if "query_analytics" not in beta_tools:
        raise SystemExit(f"Expected beta query to use SQL analytics, got {beta_tools}")


if __name__ == "__main__":
    asyncio.run(main())
