from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from .fetch_web.fetch import fetch_web
from .mcp.factory import build_mcp_tools
from .reminders import cancel_reminder, create_reminder, list_reminders

BUILTIN_TOOLS = [fetch_web, create_reminder, list_reminders, cancel_reminder]


class ToolRegistry:
    def __init__(self, enabled: list[str] | None = None, config: dict[str, Any] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in BUILTIN_TOOLS:
            if enabled is None or tool.name in enabled:
                self.register(tool)
        if config is not None:
            for tool in build_mcp_tools(config=config, enabled=enabled):
                self.register(tool)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def run(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name].invoke(arguments)
