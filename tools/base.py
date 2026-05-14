from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode


Tool = BaseTool


def build_tool_node(tools: list[BaseTool]) -> ToolNode:
    return ToolNode(tools)

