from __future__ import annotations

import os

RAW_DATABASE_URL = os.getenv("ANALYTICS_DATABASE_URL") or os.environ["DATABASE_URL"]
DATABASE_URL = RAW_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
