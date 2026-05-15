from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from .config_loader import load_config
from .nodes import AgentNodes


class AgentWorkflow:
    """Agent 工作流构建类"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_config()
        self.nodes = AgentNodes(self.config)
        self.graph: StateGraph | None = None

    def build_basic_workflow(self, model: Runnable) -> StateGraph:
        class AgentState(dict):
            messages: list[BaseMessage]
            next: str

        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("agent", self.nodes.get_agent_node(model))
        workflow.add_node("tools", self.nodes.get_tool_node())

        # 添加边
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )
        workflow.add_edge("tools", "agent")

        self.graph = workflow
        return workflow

    def build_advanced_workflow(self, model: Runnable) -> StateGraph:
        """构建高级工作流：包含记忆和路由"""

        # 定义状态类型
        class AdvancedAgentState(dict):
            messages: list[BaseMessage]
            memory: dict[str, Any]
            next: str

        # 创建图
        workflow = StateGraph(AdvancedAgentState)

        # 添加节点
        workflow.add_node("agent", self.nodes.get_agent_node(model))
        workflow.add_node("tools", self.nodes.get_tool_node())
        workflow.add_node("memory", self.nodes.get_memory_node())
        workflow.add_node("router", self.nodes.get_routing_node())

        # 添加边
        workflow.add_edge(START, "router")

        # 路由逻辑
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "agent": "agent",
                "memory": "memory",
                "end": END,
            },
        )

        # Agent 逻辑
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )

        workflow.add_edge("tools", "memory")
        workflow.add_edge("memory", "agent")

        self.graph = workflow
        return workflow

    def _should_continue(self, state: dict[str, Any]) -> str:
        """判断是否需要继续执行工具调用"""
        if state.get("routing", {}).get("use_tool"):
            return "continue"

        messages = state.get("messages", [])
        if not messages:
            return "end"

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        return "end"

    def _route_decision(self, state: dict[str, Any]) -> str:
        """路由决策逻辑"""
        if not state.get("messages"):
            return "end"

        destination = state.get("routing", {}).get("destination")
        if destination == "memory":
            return "memory"
        return "agent"

    def compile(self) -> Runnable:
        """编译工作流为可执行的 Runnable"""
        if self.graph is None:
            raise ValueError("Workflow not built. Call build_basic_workflow() or build_advanced_workflow() first.")
        return self.graph.compile()

    def get_graph(self) -> StateGraph:
        """获取构建的图"""
        if self.graph is None:
            raise ValueError("Workflow not built.")
        return self.graph