from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from langgraph.graph import END, START, StateGraph

from agent.nodes.planner import planner_node
from agent.nodes.retrieval import create_retrieval_node
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
        "run_id": "test-002",
        "token_usage": {},
    }

    doc_retrieval_node = create_retrieval_node("http://127.0.0.1:8081", "search_documents")

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("doc_retrieval", doc_retrieval_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "doc_retrieval")
    graph.add_edge("doc_retrieval", END)
    app = graph.compile()

    result = await app.ainvoke(initial_state)
    print("doc_context:", result["doc_context"])

    if not result["doc_context"]:
        raise SystemExit("Expected document context from the RAG MCP server")


if __name__ == "__main__":
    asyncio.run(main())
