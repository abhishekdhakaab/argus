from __future__ import annotations

import os

DEFAULT_DOC_MCP_URL = os.getenv("DOC_MCP_URL", "http://127.0.0.1:8081")
DEFAULT_SQL_MCP_URL = os.getenv("SQL_MCP_URL", "http://127.0.0.1:8082")
DEFAULT_EXTERNAL_API_MCP_URL = os.getenv("EXTERNAL_API_MCP_URL", "http://127.0.0.1:8083")
OPENAI_CHAT_COMPLETIONS_URL = os.getenv(
    "OPENAI_CHAT_COMPLETIONS_URL",
    "https://api.openai.com/v1/chat/completions",
)

DEFAULT_SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "gpt-4o-mini")

# Pricing changes independently of synthesis behavior, so it stays configurable.
INPUT_COST_PER_1K = float(os.getenv("SYNTHESIS_INPUT_COST_PER_1K", "0.00015"))
OUTPUT_COST_PER_1K = float(os.getenv("SYNTHESIS_OUTPUT_COST_PER_1K", "0.00060"))
