from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable


def route_markdown_ids(
    content: str,
    route_llm: Runnable,
    config: dict[str, Any],
    candidate_ids: list[str] | None = None,
) -> list[str]:
    items = config.get("memory", {}).get("markdown_files", [])
    candidate_set = set(candidate_ids or [])
    allowed_ids = [
        item.get("id", "")
        for item in items
        if item.get("id") and (not candidate_set or item.get("id") in candidate_set)
    ]
    options = [
        {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "purpose": item.get("purpose", ""),
        }
        for item in items
        if item.get("id") in allowed_ids
    ]
    if not allowed_ids:
        return []

    response = route_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You choose which cold markdown memory files should be read.\n"
                    "Return JSON only: {\"memory_ids\": [\"...\"]}.\n"
                    "Only choose from allowed ids. Keep list short and relevant.\n"
                    "Choose stable long-term memory only when it helps the current request.\n"
                    "Route core only when the user explicitly needs older archived context.\n"
                    "Do not route history or pending; history belongs to DB and pending belongs to Redis."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {"content": content, "memory_options": options, "allowed_ids": allowed_ids},
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


def route_markdown_entry_ids(
    content: str,
    route_llm: Runnable,
    memory_id: str,
    entries: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    options = [
        {
            "entry_id": str(entry.get("entry_id", "")),
            "section": str(entry.get("section", "")),
            "modified_at": str(entry.get("modified_at", "") or entry.get("created", "")),
            "body": str(entry.get("body", ""))[:240],
        }
        for entry in entries
        if entry.get("entry_id") and entry.get("body")
    ]
    allowed_ids = [item["entry_id"] for item in options]
    if not allowed_ids or limit <= 0:
        return []

    response = route_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You choose which individual cold-memory entries should be injected into the system prompt.\n"
                    "Return JSON only: {\"entry_ids\": [\"...\"]}.\n"
                    "Only choose from allowed entry_ids.\n"
                    "Choose at most the requested limit.\n"
                    "When same-type entries conflict, prefer the newer modified_at timestamp.\n"
                    "For self memory, choose only behavior rules relevant to the current turn; do not choose every rule by default."
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "content": content,
                        "memory_id": memory_id,
                        "limit": limit,
                        "entry_options": options,
                        "allowed_ids": allowed_ids,
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )
    payload = _parse_json(_extract_text(response))
    entry_ids = payload.get("entry_ids", [])
    if not isinstance(entry_ids, list):
        return []

    selected: list[str] = []
    for value in entry_ids:
        if isinstance(value, str) and value in allowed_ids and value not in selected:
            selected.append(value)
        if len(selected) >= limit:
            break
    return selected


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
