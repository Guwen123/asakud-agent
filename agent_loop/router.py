from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from .config_loader import load_config
from .model_factory import build_chat_model


ROUTER_PROMPT = (
    "You are a workflow router. Return JSON only.\n"
    "Fields:\n"
    "- read_md: true/false\n"
    "- read_rag: true/false\n"
    "- use_tool: true/false\n"
    "- read_md_after_tool: true/false\n"
    "- rag_mode: direct or hybrid_rerank\n"
    "- plan: short text\n"
)


def get_routing_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_chat_model(cfg, model_key="route_model")

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        content = ""
        if messages:
            content = str(getattr(messages[-1], "content", "") or "")

        response = route_llm.invoke(
            [
                SystemMessage(content=ROUTER_PROMPT),
                HumanMessage(content=json.dumps({"content": content}, ensure_ascii=False)),
            ]
        )
        payload = _parse_router_payload(_extract_text(response))
        state["routing"] = payload
        return state

    return RunnableLambda(_run)


def _parse_router_payload(text: str) -> dict[str, Any]:
    payload = _parse_json(text)
    rag_mode = str(payload.get("rag_mode", "direct")).strip().lower()
    if rag_mode not in {"direct", "hybrid_rerank"}:
        rag_mode = "direct"
    return {
        "read_md": bool(payload.get("read_md", True)),
        "read_rag": bool(payload.get("read_rag", False)),
        "use_tool": bool(payload.get("use_tool", False)),
        "read_md_after_tool": bool(payload.get("read_md_after_tool", False)),
        "rag_mode": rag_mode,
        "plan": str(payload.get("plan", "")),
    }


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(response, str):
        return response
    return str(response)


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

