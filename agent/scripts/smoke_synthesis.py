from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from agent.graph import build_doc_graph
from agent.state import AgentState


async def main() -> None:
    initial_state: AgentState = {
        "query": "What was cloud spending in Q3?",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "plan": [],
        "doc_context": [],
        "sql_context": [],
        "api_context": [],
        "answer": "",
        "run_id": "test-003",
        "token_usage": {},
    }

    app = build_doc_graph()
    result = await app.ainvoke(initial_state)
    print("Answer:", result["answer"])
    print("Tokens:", result["token_usage"])

    usage = result["token_usage"]
    if not result["answer"]:
        raise SystemExit("Expected a non-empty answer")
    if "cloud" not in result["answer"].lower():
        raise SystemExit("Expected the answer to reference the retrieved cloud context")
    if usage["input_tokens"] <= 0 or usage["output_tokens"] <= 0:
        raise SystemExit(f"Expected non-zero tokens, got {usage}")
    if usage["cost_usd"] <= 0:
        raise SystemExit(f"Expected positive cost, got {usage}")


if __name__ == "__main__":
    asyncio.run(main())
