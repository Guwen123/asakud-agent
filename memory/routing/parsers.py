from __future__ import annotations

import json
import re
from typing import Any

from memory.schemas import DESTINATION_TO_MEMORY_ID, StorageDestination, StorageRouteDecision


def parse_json_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        raise ValueError(f"LLM did not return JSON: {text!r}")
    return json.loads(match.group(0))


def extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(response, str):
        return response
    return str(response)


def normalize_storage_decision(
    payload: dict[str, Any],
    original_content: str,
) -> StorageRouteDecision:
    destination = normalize_destination(payload.get("destination"))
    should_store = bool(payload.get("should_store", destination not in {"none"}))

    if not should_store:
        destination = "none"

    memory_id = payload.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id:
        memory_id = DESTINATION_TO_MEMORY_ID[destination]

    section = payload.get("section")
    if not isinstance(section, str) or not section:
        section = None

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason:
        reason = "LLM did not provide a reason."

    routed_content = payload.get("content")
    if not isinstance(routed_content, str) or not routed_content.strip():
        routed_content = original_content

    return StorageRouteDecision(
        should_store=should_store,
        destination=destination,
        memory_id=memory_id,
        section=section,
        reason=reason,
        content=routed_content.strip(),
    )


def normalize_destination(value: Any) -> StorageDestination:
    if isinstance(value, str):
        normalized = value.strip().lower()
        aliases = {
            "user": "user_memory",
            "project": "project_memory",
            "decision": "decision_memory",
            "decisions": "decision_memory",
            "scheduled": "scheduled_task",
            "schedule": "scheduled_task",
            "rag_memory": "rag",
            "session": "session_memory",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in DESTINATION_TO_MEMORY_ID:
            return normalized  # type: ignore[return-value]
    return "none"

