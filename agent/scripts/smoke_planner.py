from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent.nodes.planner import planner_node
from agent.state import AgentState


async def main() -> None:
    state: AgentState = {
        "query": "What was cloud spending in Q3?",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "plan": [],
        "doc_context": [],
        "sql_context": [],
        "api_context": [],
        "answer": "",
        "run_id": "test-001",
        "token_usage": {},
    }
    result = await planner_node(state)
    plan = result["plan"]
    if not plan:
        raise ValueError("Planner returned an empty plan.")
    tools = {item["tool"] for item in plan}
    if not {"query_analytics", "search_documents"} & tools:
        raise ValueError(f"Expected query_analytics or search_documents, got {tools}.")
    print("Plan:", plan)


if __name__ == "__main__":
    asyncio.run(main())
