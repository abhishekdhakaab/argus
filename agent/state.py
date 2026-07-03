from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict


class AgentState(TypedDict):
    query: str
    tenant_id: str
    plan: list[dict]
    doc_context: Annotated[list[str], operator.add]
    sql_context: Annotated[list[str], operator.add]
    api_context: Annotated[list[str], operator.add]
    answer: str
    run_id: str
    token_usage: dict
    active_sub_query: NotRequired[str]
