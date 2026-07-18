from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from .client import MCPHttpClient


DEFAULT_MCP_SERVER: dict[str, Any] = {
    "name": "local-mcp-example",
    "enabled": False,
    "base_url": "http://127.0.0.1:9000",
    "transport": "mcp-jsonrpc",
    "endpoint": "/mcp",
    "timeout_seconds": 5,
    "headers": {},
    "notes": "Disabled example only. Start a real MCP HTTP gateway before enabling.",
}


def build_mcp_tools(config: dict[str, Any], enabled: list[str] | None = None) -> list[BaseTool]:
    mcp_cfg = config.get("mcp", {})
    if not isinstance(mcp_cfg, dict) or not mcp_cfg.get("enabled", False):
        return []

    tools: list[BaseTool] = []
    for server in configured_mcp_servers(config):
        if not isinstance(server, dict):
            continue
        tools.extend(_build_server_tools(server, enabled))
    return tools


def configured_mcp_servers(config: dict[str, Any]) -> list[dict[str, Any]]:
    mcp_cfg = config.get("mcp", {})
    if not isinstance(mcp_cfg, dict):
        return []
    servers = mcp_cfg.get("servers", [])
    if not isinstance(servers, list) or not servers:
        return [dict(DEFAULT_MCP_SERVER)] if bool(mcp_cfg.get("use_default_server", False)) else []
    return [server for server in servers if isinstance(server, dict)]


def list_mcp_server_tools(server: dict[str, Any]) -> list[dict[str, Any]]:
    client = _client_from_server(server)
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
        }
        for spec in client.list_tools()
    ]


def _build_server_tools(server: dict[str, Any], enabled: list[str] | None) -> list[BaseTool]:
    if not bool(server.get("enabled", True)):
        return []

    base_url = str(server.get("base_url", "")).strip()
    if not base_url:
        return []

    server_name = _normalize_server_name(str(server.get("name", "mcp") or "mcp"))
    client = _client_from_server(server)

    try:
        specs = client.list_tools()
    except Exception:
        return []

    allowed_remote_tools = set(_string_list(server.get("allowed_tools", [])))
    out: list[BaseTool] = []
    for spec in specs:
        if allowed_remote_tools and spec.name not in allowed_remote_tools:
            continue
        tool_name = f"mcp.{server_name}.{spec.name}"
        if not _mcp_tool_enabled(enabled, server_name, spec.name, tool_name):
            continue
        out.append(_make_mcp_tool(client, tool_name, spec.name, spec.description, server_name))
    return out


def _client_from_server(server: dict[str, Any]) -> MCPHttpClient:
    headers = server.get("headers", {})
    if not isinstance(headers, dict):
        headers = {}

    list_req = server.get("list_tools_request", {})
    call_req = server.get("call_tool_request", {})
    if not isinstance(list_req, dict):
        list_req = {}
    if not isinstance(call_req, dict):
        call_req = {}

    return MCPHttpClient(
        base_url=str(server.get("base_url", "") or ""),
        timeout_seconds=float(server.get("timeout_seconds", 10) or 10),
        headers={str(key): str(value) for key, value in headers.items()},
        transport=str(server.get("transport", "mcp-jsonrpc") or "mcp-jsonrpc"),
        endpoint=str(server.get("endpoint", "/mcp") or "/mcp"),
        tools_path=str(list_req.get("path", server.get("tools_path", "/tools")) or "/tools"),
        call_path=str(call_req.get("path", server.get("call_path", "/tools/call")) or "/tools/call"),
        list_method=str(list_req.get("method", "GET") or "GET"),
        call_method=str(call_req.get("method", "POST") or "POST"),
    )


def _make_mcp_tool(
    client: MCPHttpClient,
    tool_name: str,
    remote_name: str,
    description: str,
    server_name: str,
) -> BaseTool:
    def _invoke(**kwargs: Any) -> Any:
        return client.call_tool(name=remote_name, arguments=kwargs)

    return StructuredTool.from_function(
        func=_invoke,
        name=tool_name,
        description=description or f"MCP tool `{remote_name}` from server `{server_name}`.",
    )


def _mcp_tool_enabled(enabled: list[str] | None, server_name: str, remote_name: str, full_name: str) -> bool:
    if enabled is None:
        return True
    enabled_set = set(_string_list(enabled))
    if not enabled_set:
        return False
    return any(
        item in enabled_set
        for item in (
            "mcp",
            "mcp.*",
            f"mcp.{server_name}",
            f"mcp.{server_name}.*",
            full_name,
            remote_name,
        )
    )


def _normalize_server_name(value: str) -> str:
    import re

    lowered = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    return re.sub(r"-{2,}", "-", normalized).strip("-") or "mcp"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]
