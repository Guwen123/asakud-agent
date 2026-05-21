from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPHttpClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = headers or {}

    def list_tools(self) -> list[MCPToolSpec]:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds, headers=self.headers) as client:
            resp = client.get("/tools")
            resp.raise_for_status()
            payload = resp.json()
        tools = payload.get("tools", []) if isinstance(payload, dict) else []
        specs: list[MCPToolSpec] = []
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            specs.append(
                MCPToolSpec(
                    name=name,
                    description=str(item.get("description", "") or ""),
                    input_schema=item.get("input_schema", {}) if isinstance(item.get("input_schema"), dict) else {},
                )
            )
        return specs

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        body = {"name": name, "arguments": arguments or {}}
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds, headers=self.headers) as client:
            resp = client.post("/tools/call", json=body)
            resp.raise_for_status()
            payload = resp.json()
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload
