from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from rag.retriever import routed_retrieve

from ..config_loader import load_config
from ..models.factory import build_route_model


def get_rag_memory_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 250})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        routing = state.get("routing", {})
        if not routing.get("read_rag", False):
            return state
        rag_index = state.get("rag_index")
        if rag_index is None:
            return state
        content = str(state.get("user_input", "") or "")
        if not content:
            return state
        result = routed_retrieve(
            query=content,
            index=rag_index,
            route_llm=route_llm,
            fallback_route=routing.get("rag_mode", "direct"),
        )
        memory = state.get("memory", {})
        memory["rag"] = [item.chunk.text for item in result.results]
        memory["rag_route"] = result.route
        state["memory"] = memory
        return state

    return RunnableLambda(_run)
