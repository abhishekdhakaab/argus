from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    query: str = Field(min_length=1)


class QueryResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: str
    answer: str
    status: str


class QueryRunResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: str
    query: str
    answer: str | None
    status: str
    cost_usd: float | None
    latency_ms: int | None
    tools_used: list[str] | None
