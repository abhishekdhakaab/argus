from __future__ import annotations

from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

from agent.config import DEFAULT_DOC_MCP_URL, DEFAULT_EXTERNAL_API_MCP_URL, DEFAULT_SQL_MCP_URL
from agent.nodes.planner import planner_node
from agent.nodes.retrieval import create_retrieval_node
from agent.nodes.synthesis import synthesis_node
from agent.state import AgentState


def build_doc_graph(doc_mcp_url: str = DEFAULT_DOC_MCP_URL):
    doc_retrieval_node = create_retrieval_node(doc_mcp_url, "search_documents")

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("doc_retrieval", doc_retrieval_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "doc_retrieval")
    graph.add_edge("doc_retrieval", "synthesis")
    graph.add_edge("synthesis", END)
    return graph.compile()


def build_agent_graph(
    doc_mcp_url: str = DEFAULT_DOC_MCP_URL,
    sql_mcp_url: str = DEFAULT_SQL_MCP_URL,
    external_api_mcp_url: str = DEFAULT_EXTERNAL_API_MCP_URL,
):
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("doc_retrieval", create_retrieval_node(doc_mcp_url, "search_documents"))
    graph.add_node("sql_retrieval", create_retrieval_node(sql_mcp_url, "query_analytics"))
    graph.add_node("api_retrieval", create_retrieval_node(external_api_mcp_url, "fetch_external_data"))
    graph.add_node("synthesis", synthesis_node)
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_to_retrievals)
    graph.add_edge("doc_retrieval", "synthesis")
    graph.add_edge("sql_retrieval", "synthesis")
    graph.add_edge("api_retrieval", "synthesis")
    graph.add_edge("synthesis", END)
    return graph.compile()


def route_to_retrievals(state: AgentState) -> list[Send]:
    sends: list[Send] = []
    for plan_item in state["plan"]:
        if plan_item["tool"] == "search_documents":
            sends.append(Send("doc_retrieval", {**state, "active_sub_query": plan_item["sub_query"]}))
        elif plan_item["tool"] == "query_analytics":
            sends.append(Send("sql_retrieval", {**state, "active_sub_query": plan_item["sub_query"]}))
        elif plan_item["tool"] == "fetch_external_data":
            sends.append(Send("api_retrieval", {**state, "active_sub_query": plan_item["sub_query"]}))

    return sends if sends else [Send("synthesis", state)]
