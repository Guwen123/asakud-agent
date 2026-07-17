from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent_loop.config_loader import project_path
from agent_loop.models.factory import build_chat_model
from tools.registry import ToolRegistry


SKILL_RUNNER_SYSTEM_PROMPT = """You are a focused executable-skill sub-agent.

Use the selected skill package to solve the user's request.

Rules:
- Follow the skill instructions and references.
- Use tools when the skill requires external information or concrete actions.
- Return only the task result for the main workflow to style later.
- Do not imitate any persona or final speaking style.
- If the skill package is insufficient, say what is missing instead of inventing facts.
"""


class SkillRunnerAgent:
    """Runs non-style skills outside the main workflow context."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.tool_registry = ToolRegistry(config.get("tools", {}).get("enabled"), config=config)

    def run(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str = "",
    ) -> dict[str, Any]:
        script_result = self._run_script_entry(
            skill_entry=skill_entry,
            skill_bundle=skill_bundle,
            user_input=user_input,
            recent_summary=recent_summary,
        )
        if script_result.get("handled"):
            return script_result

        return self._run_llm_skill(
            skill_entry=skill_entry,
            skill_bundle=skill_bundle,
            user_input=user_input,
            recent_summary=recent_summary,
        )

    def _run_script_entry(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str,
    ) -> dict[str, Any]:
        entry = str(skill_entry.get("entry", "") or "").strip()
        if not entry:
            return {"handled": False, "reason": "missing_entry"}

        try:
            func = _load_entry_callable(skill_entry, entry)
            raw = func(
                {
                    "config": self.config,
                    "skill": skill_entry,
                    "skill_bundle": skill_bundle,
                    "user_input": user_input,
                    "recent_summary": recent_summary,
                }
            )
            output = raw.get("output", "") if isinstance(raw, dict) else str(raw or "")
            return {
                "handled": bool(str(output).strip()),
                "mode": "script",
                "skill_id": str(skill_entry.get("id", "") or ""),
                "output": str(output).strip(),
                "raw": raw if isinstance(raw, dict) else {},
            }
        except Exception as exc:
            return {
                "handled": False,
                "mode": "script",
                "skill_id": str(skill_entry.get("id", "") or ""),
                "error": str(exc),
            }

    def _run_llm_skill(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str,
    ) -> dict[str, Any]:
        max_steps = int(skill_entry.get("max_steps") or self.config.get("skill_runner", {}).get("max_steps", 8))
        model = build_chat_model(
            self.config,
            overrides={
                "temperature": float(self.config.get("skill_runner", {}).get("temperature", 0.0)),
                "max_output_tokens": int(self.config.get("skill_runner", {}).get("max_output_tokens", 2048)),
            },
        ).bind_tools(self.tool_registry.tools())

        messages: list[Any] = [
            SystemMessage(content=SKILL_RUNNER_SYSTEM_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {
                        "skill": _public_skill_payload(skill_entry),
                        "skill_package": skill_bundle,
                        "recent_summary": recent_summary,
                        "user_input": user_input,
                    },
                    ensure_ascii=False,
                )
            ),
        ]

        last_response: Any = None
        for _ in range(max_steps):
            last_response = model.invoke(messages)
            messages.append(last_response)
            if not isinstance(last_response, AIMessage) or not last_response.tool_calls:
                break

            for call in last_response.tool_calls:
                name = str(call.get("name", ""))
                args = call.get("args", {})
                call_id = str(call.get("id", ""))
                if not isinstance(args, dict):
                    args = {}
                try:
                    result = self.tool_registry.run(name, args)
                except Exception as exc:
                    result = {"error": str(exc), "tool": name}
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=call_id,
                    )
                )

        output = _extract_text(last_response).strip()
        return {
            "handled": bool(output),
            "mode": "llm",
            "skill_id": str(skill_entry.get("id", "") or ""),
            "output": output,
        }


def _load_entry_callable(skill_entry: dict[str, Any], entry: str) -> Callable[[dict[str, Any]], Any]:
    if ":" not in entry:
        raise ValueError("skill entry must use 'relative/path.py:function_name'")

    path_text, function_name = entry.split(":", 1)
    function_name = function_name.strip()
    if not function_name:
        raise ValueError("skill entry function name is required")

    skill_path = project_path(str(skill_entry.get("path", "") or ""))
    skill_root = skill_path.parent if skill_path.exists() else project_path("skills")
    entry_path = (skill_root / path_text.strip()).resolve()
    root_path = skill_root.resolve()
    if root_path not in entry_path.parents and entry_path != root_path:
        raise ValueError("skill entry must stay inside the skill package directory")
    if not entry_path.exists() or entry_path.suffix.lower() != ".py":
        raise FileNotFoundError(f"skill entry not found: {entry_path}")

    module_name = f"_skill_runner_{skill_entry.get('id', 'skill')}_{entry_path.stem}".replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load skill entry: {entry_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, function_name, None)
    if not callable(func):
        raise AttributeError(f"skill entry function is not callable: {function_name}")
    return func


def _public_skill_payload(skill_entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(skill_entry.get("id", "") or ""),
        "summary": str(skill_entry.get("summary", "") or ""),
        "type": str(skill_entry.get("type", "workflow") or "workflow"),
        "tools": skill_entry.get("tools", []),
        "references": skill_entry.get("references", []),
    }


def _extract_text(response: Any) -> str:
    if response is None:
        return ""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)
