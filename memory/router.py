from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable


def route_markdown_ids(content: str, route_llm: Runnable, config: dict[str, Any]) -> list[str]:
    items = config.get("memory", {}).get("markdown_files", [])
    allowed_ids = [item.get("id", "") for item in items if item.get("id")]
    if not allowed_ids:
        return []

    response = route_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You choose which markdown memory files should be read.\n"
                    "Return JSON only: {\"memory_ids\": [\"...\"]}.\n"
                    "Only choose from allowed ids. Keep list short and relevant."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {"content": content, "allowed_ids": allowed_ids},
                    ensure_ascii=False,
                )
            ),
        ]
    )
    payload = _parse_json(_extract_text(response))
    memory_ids = payload.get("memory_ids", [])
    if not isinstance(memory_ids, list):
        return []

    normalized: list[str] = []
    for value in memory_ids:
        if isinstance(value, str) and value in allowed_ids and value not in normalized:
            normalized.append(value)
    return normalized


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

