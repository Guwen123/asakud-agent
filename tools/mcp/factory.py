from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from .client import MCPHttpClient


def build_mcp_tools(config: dict[str, Any], enabled: list[str] | None = None) -> list[BaseTool]:
    mcp_cfg = config.get("mcp", {})
    if not isinstance(mcp_cfg, dict) or not mcp_cfg.get("enabled", False):
        return []

    servers = mcp_cfg.get("servers", [])
    if not isinstance(servers, list):
        return []

    tools: list[BaseTool] = []
    for server in servers:
        if not isinstance(server, dict):
            continue
        tools.extend(_build_server_tools(server, enabled))
    return tools


def _build_server_tools(server: dict[str, Any], enabled: list[str] | None) -> list[BaseTool]:
    base_url = str(server.get("base_url", "")).strip()
    if not base_url:
        return []

    server_name = str(server.get("name", "mcp")).strip() or "mcp"
    headers = server.get("headers", {})
    if not isinstance(headers, dict):
        headers = {}
    timeout = float(server.get("timeout_seconds", 30))
    client = MCPHttpClient(base_url=base_url, timeout_seconds=timeout, headers=headers)

    try:
        specs = client.list_tools()
    except Exception:
        return []

    out: list[BaseTool] = []
    for spec in specs:
        tool_name = f"mcp.{server_name}.{spec.name}"
        if enabled is not None and tool_name not in enabled:
            continue
        out.append(_make_mcp_tool(client, tool_name, spec.name, spec.description))
    return out


def _make_mcp_tool(
    client: MCPHttpClient,
    tool_name: str,
    remote_name: str,
    description: str,
) -> BaseTool:
    def _invoke(**kwargs: Any) -> Any:
        return client.call_tool(name=remote_name, arguments=kwargs)

    return StructuredTool.from_function(
        func=_invoke,
        name=tool_name,
        description=description or f"MCP tool: {remote_name}",
    )
