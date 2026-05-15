from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from tools.registry import ToolRegistry

try:
    from .router import get_routing_node as _get_routing_node
    from .memory import get_memory_node as _get_memory_node
except Exception:
    _get_routing_node = None
    _get_memory_node = None


class AgentNodes:
    """LangGraph 节点导入和管理类"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tool_registry = ToolRegistry(config.get("tools", {}).get("enabled"))
        self._nodes: dict[str, Runnable] = {}

    def get_tool_node(self) -> ToolNode:
        """获取工具节点"""
        return self.tool_registry.to_tool_node()

    def get_agent_node(self, model: Runnable) -> Runnable:
        """获取 Agent 节点"""

        return model

    def get_memory_node(self) -> Runnable:
        """获取记忆节点"""
        if _get_memory_node is None:
            raise RuntimeError("memory node implementation not available")
        return _get_memory_node(self.config)

    def get_routing_node(self) -> Runnable:
        """获取路由节点"""
        if _get_routing_node is None:
            raise RuntimeError("routing node implementation not available")
        return _get_routing_node(self.config)

    def register_node(self, name: str, node: Runnable) -> None:
        """注册自定义节点"""
        self._nodes[name] = node

    def get_node(self, name: str) -> Runnable:
        """获取已注册的节点"""
        return self._nodes[name]

    def list_nodes(self) -> list[str]:
        """列出所有可用节点"""
        return list(self._nodes.keys())