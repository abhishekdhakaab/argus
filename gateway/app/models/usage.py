from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UsageResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    queries_today: int
    avg_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: float
    avg_cost_per_query: float
    top_tools: list[str]
