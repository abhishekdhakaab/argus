from __future__ import annotations

import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("LEGACY_CIRCUIT_FAILURE_THRESHOLD", "5"))
CIRCUIT_WINDOW_SECONDS = int(os.getenv("LEGACY_CIRCUIT_WINDOW_SECONDS", "60"))
CIRCUIT_COOLDOWN_SECONDS = int(os.getenv("LEGACY_CIRCUIT_COOLDOWN_SECONDS", "30"))
