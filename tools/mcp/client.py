from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPHttpClient:
    """Small HTTP client that supports common MCP gateway shapes.

    Supported transports:
    - `mcp-jsonrpc` / `jsonrpc` / `streamable-http`: POST JSON-RPC to an endpoint such as `/mcp`.
    - `simple-http`: GET/POST REST-like gateway endpoints such as `/tools` and `/tools/call`.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        headers: dict[str, str] | None = None,
        transport: str = "mcp-jsonrpc",
        endpoint: str = "/mcp",
        tools_path: str = "/tools",
        call_path: str = "/tools/call",
        list_method: str = "GET",
        call_method: str = "POST",
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = headers or {}
        self.transport = str(transport or "mcp-jsonrpc").lower()
        self.endpoint = _normalize_path(endpoint or "/mcp")
        self.tools_path = _normalize_path(tools_path or "/tools")
        self.call_path = _normalize_path(call_path or "/tools/call")
        self.list_method = str(list_method or "GET").upper()
        self.call_method = str(call_method or "POST").upper()
        self._session_id = ""
        self._initialized = False

    def list_tools(self) -> list[MCPToolSpec]:
        if self._uses_jsonrpc():
            payload = self._jsonrpc_request("tools/list", {})
        else:
            payload = self._simple_request(
                method=self.list_method,
                path=self.tools_path,
                json_body={},
            )
        return _parse_tool_specs(payload)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("MCP tool name is required")
        args = arguments or {}
        if self._uses_jsonrpc():
            payload = self._jsonrpc_request(
                "tools/call",
                {
                    "name": clean_name,
                    "arguments": args,
                },
            )
        else:
            payload = self._simple_request(
                method=self.call_method,
                path=self.call_path,
                json_body={
                    "name": clean_name,
                    "arguments": args,
                },
            )
        return _normalize_tool_result(payload)

    def _uses_jsonrpc(self) -> bool:
        return self.transport in {"mcp-jsonrpc", "jsonrpc", "streamable-http", "streamable_http"}

    def _jsonrpc_request(self, method: str, params: dict[str, Any]) -> Any:
        if method not in {"initialize", "notifications/initialized"}:
            self._ensure_initialized()
        return self._raw_jsonrpc_request(method, params, expect_response=True)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            self._raw_jsonrpc_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "asakud-agent",
                        "version": "0.1.0",
                    },
                },
                expect_response=True,
            )
            self._raw_jsonrpc_request("notifications/initialized", {}, expect_response=False)
        except Exception:
            # Some simple JSON-RPC gateways do not implement the full MCP
            # handshake. Fall back to direct tools/list and tools/call.
            pass
        self._initialized = True

    def _raw_jsonrpc_request(self, method: str, params: dict[str, Any], *, expect_response: bool) -> Any:
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        if expect_response:
            body["id"] = str(uuid.uuid4())
        payload = self._simple_request("POST", self.endpoint, body)
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(json.dumps(payload["error"], ensure_ascii=False))
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    def _simple_request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        if not self.base_url:
            raise ValueError("MCP base_url is required")
        request_method = str(method or "GET").upper()
        headers = dict(self.headers)
        if self._uses_jsonrpc():
            headers.setdefault("Accept", "application/json, text/event-stream")
            headers.setdefault("Content-Type", "application/json")
        if self._session_id:
            headers.setdefault("Mcp-Session-Id", self._session_id)
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds, headers=headers) as client:
            if request_method == "GET":
                resp = client.get(path)
            elif request_method == "POST":
                resp = client.post(path, json=json_body or {})
            else:
                resp = client.request(request_method, path, json=json_body or {})
            resp.raise_for_status()
            session_id = resp.headers.get("Mcp-Session-Id")
            if session_id:
                self._session_id = session_id
            if not resp.content:
                return {}
            return _decode_response_payload(resp)


def _parse_tool_specs(payload: Any) -> list[MCPToolSpec]:
    result = _unwrap_result(payload)
    if isinstance(result, dict):
        tools = result.get("tools", [])
    elif isinstance(result, list):
        tools = result
    else:
        tools = []

    specs: list[MCPToolSpec] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        input_schema = item.get("inputSchema") or item.get("input_schema") or item.get("schema") or {}
        specs.append(
            MCPToolSpec(
                name=name,
                description=str(item.get("description", "") or ""),
                input_schema=input_schema if isinstance(input_schema, dict) else {},
            )
        )
    return specs


def _normalize_tool_result(payload: Any) -> Any:
    result = _unwrap_result(payload)
    if not isinstance(result, dict):
        return result

    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            if "text" in item:
                parts.append(str(item.get("text", "")))
            elif "json" in item:
                parts.append(json.dumps(item.get("json"), ensure_ascii=False))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(part for part in parts if part)

    if "result" in result:
        return result["result"]
    return result


def _decode_response_payload(resp: httpx.Response) -> Any:
    content_type = resp.headers.get("content-type", "").lower()
    text = resp.text.strip()
    if "text/event-stream" in content_type or text.startswith("event:") or "\ndata:" in text:
        return _decode_sse_payload(text)
    return resp.json()


def _decode_sse_payload(text: str) -> Any:
    data_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data_lines.append(stripped[5:].strip())
    if not data_lines:
        return {}
    raw = "\n".join(data_lines).strip()
    if raw == "[DONE]":
        return {}
    return json.loads(raw)


def _unwrap_result(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def _normalize_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return "/"
    return text if text.startswith("/") else f"/{text}"
