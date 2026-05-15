from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from memory.manager import get_markdown_memory_for_content
from agent_loop.model_factory import build_chat_model
from .config_loader import load_config


def get_memory_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    storage_llm = build_chat_model(cfg, model_key="route_model")

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        content = getattr(last, "content", None) if last is not None else ""

        markdown_by_id = get_markdown_memory_for_content(content or "", storage_llm, cfg)

        memory = state.get("memory", {})
        memory["markdown"] = markdown_by_id
        state["memory"] = memory
        return state

    return RunnableLambda(_run)
