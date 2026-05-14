from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from .base import build_tool_node
from .builtin import BUILTIN_TOOLS


class ToolRegistry:
    def __init__(self, enabled: list[str] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in BUILTIN_TOOLS:
            if enabled is None or tool.name in enabled:
                self.register(tool)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_tool_node(self) -> ToolNode:
        return build_tool_node(self.tools())

    def describe(self) -> list[dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description or ""}
            for tool in self._tools.values()
        ]

    def run(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name].invoke(arguments)

