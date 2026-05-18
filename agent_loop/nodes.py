from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda

from tools.registry import ToolRegistry

from .model_factory import build_chat_model
from .memory import get_md_memory_node
from .rag_memory import get_rag_memory_node
from .router import get_routing_node


class AgentNodes:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tool_registry = ToolRegistry(config.get("tools", {}).get("enabled"))
        self.chat_model = build_chat_model(config).bind_tools(self.tool_registry.tools())

    def get_tool_node(self) -> Runnable:
        return RunnableLambda(self._run_tools)

    def get_agent_model_node(self) -> Runnable:
        return RunnableLambda(self._run_agent_model)

    def get_rag_retrieval_memory_node(self) -> Runnable:
        return get_rag_memory_node(self.config)

    def get_md_memory_node(self) -> Runnable:
        return get_md_memory_node(self.config)

    def get_router_node(self) -> Runnable:
        return get_routing_node(self.config)

    def _run_agent_model(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        user_input = str(state.get("user_input", "") or "")
        if not messages:
            messages.append(SystemMessage(content=self._build_system_message(state)))
            messages.append(HumanMessage(content=user_input))
        response = self.chat_model.invoke(messages)
        messages.append(response)
        state["messages"] = messages
        state["assistant_output"] = self._extract_text(response)
        return state

    def _run_tools(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[-1], AIMessage):
            state["messages"] = messages
            return state
        tool_calls = messages[-1].tool_calls or []
        for call in tool_calls:
            name = str(call.get("name", ""))
            args = call.get("args", {})
            call_id = str(call.get("id", ""))
            if not isinstance(args, dict):
                args = {}
            try:
                result = self.tool_registry.run(name, args)
            except Exception as exc:
                result = {"error": str(exc), "tool": name}
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call_id,
                )
            )
        state["messages"] = messages
        return state

    def _build_system_message(self, state: dict[str, Any]) -> str:
        memory = state.get("memory", {})
        md_map = memory.get("markdown", {})
        rag_items = memory.get("rag", [])
        md_text = "\n\n".join(str(v) for v in md_map.values()) if md_map else "No markdown memory loaded."
        rag_text = "\n".join(str(v) for v in rag_items) if rag_items else "No RAG memory loaded."
        return "\n".join(
            [
                f"You are {self.config['agent']['name']}.",
                self.config["agent"].get("description", ""),
                "",
                "Long-term markdown memory:",
                md_text,
                "",
                "RAG memory:",
                rag_text,
                "",
                "Available tools:",
                ", ".join(self.tool_registry.names()) if self.tool_registry.names() else "No tools enabled.",
            ]
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        return str(content)
