from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from memory.router import route_markdown_ids

from ..config_loader import load_config, project_path
from ..models.factory import build_route_model


def get_md_memory_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 250})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        routing = state.get("routing", {})
        if not routing.get("read_md", False):
            return state
        content = str(state.get("user_input", "") or "")
        selected_ids = route_markdown_ids(content=content, route_llm=route_llm, config=cfg)
        markdown_by_id = load_markdown_by_ids(cfg, selected_ids)

        memory = state.get("memory", {})
        memory["markdown"] = markdown_by_id
        memory["markdown_ids"] = selected_ids
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def load_markdown_by_ids(config: dict[str, Any], memory_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in config.get("memory", {}).get("markdown_files", []):
        memory_id = item.get("id")
        if memory_id not in memory_ids:
            continue
        path = project_path(item["path"])
        if path.exists():
            result[str(memory_id)] = path.read_text(encoding="utf-8")
    return result
