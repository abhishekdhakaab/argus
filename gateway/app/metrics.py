from __future__ import annotations

from collections import Counter

import structlog

logger = structlog.get_logger()
rate_limit_hits_total: Counter[str] = Counter()


def record_rate_limit_hit(tenant_id: str, current_window_count: int) -> None:
    rate_limit_hits_total[tenant_id] += 1
    logger.info(
        "metric_incremented",
        metric="rate_limit_hits_total",
        tenant_id=tenant_id,
        value=rate_limit_hits_total[tenant_id],
        current_window_count=current_window_count,
    )
