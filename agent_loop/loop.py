from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

try:
    from .background import start_background_workers
    from .bootstrap import bootstrap
    from .config_loader import load_config
    from .context import reset_current_message_target, set_current_message_target
    from .workflow import AgentWorkflow
except ImportError:
    from background import start_background_workers
    from bootstrap import bootstrap
    from config_loader import load_config
    from context import reset_current_message_target, set_current_message_target
    from workflow import AgentWorkflow


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def run_agent_once_async(
    user_input: str,
    message_target: dict | None = None,
    include_debug: bool = False,
) -> dict[str, Any]:
    target_token = set_current_message_target(message_target)
    try:
        return await _run_agent_once_async(user_input, include_debug=include_debug)
    finally:
        reset_current_message_target(target_token)


async def _run_agent_once_async(user_input: str, *, include_debug: bool = False) -> dict[str, Any]:
    bootstrap()
    config = load_config()
    start_background_workers(config)
    workflow = AgentWorkflow(config)
    workflow.build_workflow()
    app = workflow.compile()

    session_id = config.get("db", {}).get("default_session_id", "default")
    state = {
        "session_id": session_id,
        "original_user_input": user_input,
        "user_input": user_input,
        "messages": [HumanMessage(content=user_input)],
        "memory": {},
        "routing": {},
    }
    result = await asyncio.to_thread(app.invoke, state)
    payload: dict[str, Any] = {
        "message": str(result.get("final_output", result.get("assistant_output", "")) or ""),
        "image_ref": str(result.get("final_meme_image_ref", "") or ""),
    }
    if include_debug:
        payload["debug"] = _build_debug_payload(result)
    return payload


def run_agent_once(user_input: str) -> dict[str, Any]:
    return asyncio.run(run_agent_once_async(user_input))


def _build_debug_payload(state: dict) -> dict:
    messages = list(state.get("messages", []) or [])
    tool_calls: list[dict[str, str]] = []
    tool_results: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                tool_calls.append(
                    {
                        "name": str(call.get("name", "") or ""),
                        "id": str(call.get("id", "") or ""),
                    }
                )
        elif isinstance(message, ToolMessage):
            tool_results.append(
                {
                    "tool_call_id": str(getattr(message, "tool_call_id", "") or ""),
                    "content_preview": str(getattr(message, "content", "") or "")[:500],
                }
            )

    memory = state.get("memory", {}) if isinstance(state.get("memory", {}), dict) else {}
    return {
        "session_id": str(state.get("session_id", "") or ""),
        "history_turn_count": int(state.get("history_turn_count", 0) or 0),
        "tool_step_count": int(state.get("tool_step_count", 0) or 0),
        "tool_limit_reached": bool(state.get("tool_limit_reached", False)),
        "message_count": len(messages),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "db_snapshot": state.get("db_snapshot", {}),
        "memory_keys": sorted(str(key) for key in memory.keys()),
        "recent_summary": memory.get("recent_summary", {}),
        "memory_worker": memory.get("memory_worker", {}),
        "skill_builder": memory.get("skill_builder", {}),
        "skill_runs": memory.get("skill_runs", []),
        "performance": state.get("performance", {}),
    }


if __name__ == "__main__":
    text = input("User> ")
    print(json.dumps(run_agent_once(text), ensure_ascii=False))
