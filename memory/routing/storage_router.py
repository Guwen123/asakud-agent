from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable

from agent_loop.config_loader import load_config
from memory.markdown.targets import render_memory_targets
from memory.routing.parsers import extract_text, normalize_storage_decision, parse_json_response
from memory.routing.prompts import STORAGE_ROUTER_PROMPT
from memory.schemas import StorageRouteDecision


def route_storage_with_llm(
    content: str,
    route_llm: Runnable[Any, Any],
    context: str = "",
    config: dict | None = None,
) -> StorageRouteDecision:
    config = config or load_config()
    response = (STORAGE_ROUTER_PROMPT | route_llm).invoke(
        {
            "content": content,
            "context": context or "无",
            "memory_targets": render_memory_targets(config),
        }
    )
    payload = parse_json_response(extract_text(response))
    return normalize_storage_decision(payload, original_content=content)

