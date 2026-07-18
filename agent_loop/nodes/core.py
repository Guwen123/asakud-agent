from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda

from tools.registry import ToolRegistry

from llm.factory import build_chat_model
from prompts.system import build_hot_memory_system_prompt, build_static_system_prompt
from .memory import get_md_memory_node
from .meme import get_print_meme_node, get_router_meme_node
from .skills import RUN_SKILL_TOOL_NAME, build_skill_runner_tool, get_save_skill_node
from .style import get_style_node


class AgentNodes:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tool_registry = ToolRegistry(config.get("tools", {}).get("enabled"), config=config)
        skill_tool = build_skill_runner_tool(config)
        if skill_tool is not None:
            self.tool_registry.register(skill_tool)
        self.chat_model = build_chat_model(config).bind_tools(self.tool_registry.tools())

    def get_tool_node(self) -> Runnable:
        return RunnableLambda(self._run_tools)

    def get_agent_model_node(self) -> Runnable:
        return RunnableLambda(self._run_agent_model)

    def get_md_memory_node(self) -> Runnable:
        return get_md_memory_node(self.config)

    def get_save_skill_node(self) -> Runnable:
        return get_save_skill_node(self.config)

    def get_router_meme_node(self) -> Runnable:
        return get_router_meme_node(self.config)

    def get_print_meme_node(self) -> Runnable:
        return get_print_meme_node(self.config)

    def get_style_node(self) -> Runnable:
        return get_style_node(self.config)

    def _run_agent_model(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = self._prepare_model_messages(state)
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
        state["tool_step_count"] = self._int_state(state, "tool_step_count") + 1
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
            self._record_tool_result(state, name, result)
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call_id,
                )
            )
        state["messages"] = messages
        return state

    def _prepare_model_messages(self, state: dict[str, Any]) -> list[Any]:
        raw_messages = [
            message
            for message in list(state.get("messages", []))
            if not self._is_internal_context_message(message)
        ]
        messages = self._strip_system_prefix(raw_messages)
        static_system = SystemMessage(content=self._build_static_system_message(state))
        dynamic_messages = self._build_dynamic_context_messages(state)

        current_index = self._find_current_user_message_index(messages)
        if current_index is None:
            return [static_system, *dynamic_messages, *messages]

        prior_context = messages[:current_index]
        current_turn = messages[current_index:]
        return [static_system, *dynamic_messages, *prior_context, *current_turn]

    def _build_static_system_message(self, state: dict[str, Any]) -> str:
        memory = state.get("memory", {})
        return build_static_system_prompt(
            config=self.config,
            tool_names=self.tool_registry.names(),
            markdown_memory=memory.get("markdown", {}),
        )

    def _build_dynamic_context_messages(self, state: dict[str, Any]) -> list[SystemMessage]:
        memory = state.get("memory", {})
        messages: list[SystemMessage] = []
        hot_prompt = build_hot_memory_system_prompt(memory.get("hot_updates", {}))
        if hot_prompt:
            messages.append(SystemMessage(content=hot_prompt))
        return messages

    @staticmethod
    def _strip_system_prefix(messages: list[Any]) -> list[Any]:
        index = 0
        while index < len(messages) and isinstance(messages[index], SystemMessage):
            index += 1
        return messages[index:]

    @staticmethod
    def _find_current_user_message_index(messages: list[Any]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if isinstance(message, HumanMessage) and not AgentNodes._is_recent_summary_message(message):
                return index
        return None

    @staticmethod
    def _is_recent_summary_message(message: Any) -> bool:
        content = getattr(message, "content", "")
        return isinstance(content, str) and content.startswith("[RECENT_SUMMARY]")

    @staticmethod
    def _is_internal_context_message(message: Any) -> bool:
        content = getattr(message, "content", "")
        return isinstance(content, str) and content.startswith("[INTERNAL CONTEXT PACKAGE]")

    @staticmethod
    def _record_tool_result(state: dict[str, Any], name: str, result: Any) -> None:
        if name != RUN_SKILL_TOOL_NAME:
            return
        memory = dict(state.get("memory", {}) or {})
        skill_runs = list(memory.get("skill_runs", []) or [])
        skill_runs.append(result)
        memory["skill_runs"] = skill_runs
        state["memory"] = memory

    @staticmethod
    def _int_state(state: dict[str, Any], key: str) -> int:
        try:
            return int(state.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_text(response: Any) -> str:
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        return str(content)
