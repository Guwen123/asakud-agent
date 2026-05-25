from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from ..config_loader import load_config
from ..models.factory import build_route_model
from ..prompts import SKILL_ROUTER_PROMPT
from ..config_loader import project_path


def get_skill_memory_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 250})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        content = str(state.get("user_input", "") or "")
        selected_ids = route_skill_ids(content=content, route_llm=route_llm, config=cfg)
        skill_texts = load_skill_texts(cfg, selected_ids)
        memory = state.get("memory", {})
        memory["skills"] = skill_texts
        memory["skill_ids"] = selected_ids
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def load_skill_texts(config: dict[str, Any], skill_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in config.get("skills", []):
        skill_id = item.get("id")
        if skill_id not in skill_ids:
            continue
        path = project_path(item["path"])
        if path.exists():
            result[str(skill_id)] = path.read_text(encoding="utf-8")
    return result


def route_skill_ids(content: str, route_llm: Runnable, config: dict[str, Any]) -> list[str]:
    allowed_ids = [str(item.get("id")) for item in config.get("skills", []) if item.get("id")]
    if not allowed_ids:
        return []
    response = route_llm.invoke(
        [
            SystemMessage(content=SKILL_ROUTER_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {"content": content, "allowed_skill_ids": allowed_ids},
                    ensure_ascii=False,
                )
            ),
        ]
    )
    payload = _parse_json(_extract_text(response))
    skill_ids = payload.get("skill_ids", [])
    if not isinstance(skill_ids, list):
        return []
    normalized: list[str] = []
    for item in skill_ids:
        if isinstance(item, str) and item in allowed_ids and item not in normalized:
            normalized.append(item)
    return normalized[:2]


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
