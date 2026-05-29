from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda

from tools.registry import ToolRegistry

from ..models.factory import build_chat_model
from ..prompts import build_system_prompt
from .memory import get_md_memory_node
from .meme import get_print_meme_node, get_router_meme_node
from .rag import get_rag_memory_node
from .router import get_routing_node
from .skills import get_save_skill_node, get_skill_node


class AgentNodes:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tool_registry = ToolRegistry(config.get("tools", {}).get("enabled"), config=config)
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

    def get_skill_node(self) -> Runnable:
        return get_skill_node(self.config)

    def get_save_skill_node(self) -> Runnable:
        return get_save_skill_node(self.config)

    def get_router_meme_node(self) -> Runnable:
        return get_router_meme_node(self.config)

    def get_print_meme_node(self) -> Runnable:
        return get_print_meme_node(self.config)

    def _run_agent_model(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=self._build_system_message(state)))
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
        return build_system_prompt(
            config=self.config,
            markdown_memory=memory.get("markdown", {}),
            rag_items=memory.get("rag", []),
            skill_texts=memory.get("skills", {}),
            meme_context=memory.get("meme"),
            tool_names=self.tool_registry.names(),
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        return str(content)
