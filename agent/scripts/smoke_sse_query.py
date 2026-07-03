from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

GATEWAY_URL = "http://127.0.0.1:8080"


def post_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def auth_token() -> str:
    response = post_json(
        f"{GATEWAY_URL}/api/v1/auth/token",
        {"username": "tenant-alpha", "password": os.environ["DEV_AUTH_PASSWORD"]},
    )
    return response["access_token"]


def main() -> None:
    token = auth_token()
    body = json.dumps({"query": "what was cloud spending?"}).encode()
    req = request.Request(
        f"{GATEWAY_URL}/api/v1/query",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    raw_events: list[str] = []
    with request.urlopen(req, timeout=60) as response:
        buffer = ""
        for raw_line in response:
            line = raw_line.decode()
            print(line, end="")
            buffer += line
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                if raw_event.startswith("data: "):
                    raw_events.append(raw_event.removeprefix("data: "))

    events = [json.loads(raw_event) for raw_event in raw_events]
    event_types = [event["type"] for event in events]
    if "step" not in event_types:
        raise SystemExit(f"Expected step events, got {event_types}")
    if "token" not in event_types:
        raise SystemExit(f"Expected token events, got {event_types}")
    if not events or events[-1]["type"] != "done":
        raise SystemExit(f"Expected final done event, got {events[-1] if events else None}")
    if events[-1]["data"]["cost_usd"] <= 0 or events[-1]["data"]["latency_ms"] <= 0:
        raise SystemExit(f"Expected positive done metrics, got {events[-1]}")


if __name__ == "__main__":
    main()
