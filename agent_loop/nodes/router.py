from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from agent_loop.models.factory import build_route_model
from agent_loop.prompts import WORKFLOW_ROUTER_PROMPT

from ..config_loader import load_config


def get_routing_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 300})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        content = str(state.get("user_input", "") or "")
        response = route_llm.invoke(
            [
                SystemMessage(content=WORKFLOW_ROUTER_PROMPT),
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
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _parse_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
