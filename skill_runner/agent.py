from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from agent_loop.config_loader import project_path
from llm.factory import build_chat_model
from tools.registry import ToolRegistry

RUN_SKILL_SCRIPT_TOOL_NAME = "run_skill_script"

SKILL_RUNNER_SYSTEM_PROMPT = """You are a focused executable-skill sub-agent.

Use the selected skill package to solve the user's request.

Rules:
- First read the full skill package, including SKILL.md and extra references, before deciding the execution path.
- Follow the skill instructions and use references to increase confidence, validate assumptions, and resolve task-specific details.
- If a run_skill_script tool is available, treat it as an optional skill capability. Call it only when the skill instructions or task benefit from the executable script.
- For scripted skills, do not call external project tools directly. The executable script owns those calls through context["run_tool"].
- For non-script skills, use available project tools only when the skill package requires external information or concrete actions.
- Script entries may encapsulate tool use through context["run_tool"] when the skill declares allowed tools.
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
            allowed_tools = self._allowed_script_tools(skill_entry)
            raw = func(
                {
                    "config": self.config,
                    "skill": skill_entry,
                    "skill_bundle": skill_bundle,
                    "user_input": user_input,
                    "recent_summary": recent_summary,
                    "tools": sorted(allowed_tools),
                    "run_tool": self._script_tool_runner(allowed_tools),
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

    def _allowed_script_tools(self, skill_entry: dict[str, Any]) -> set[str]:
        available = set(self.tool_registry.names())
        requested = _string_list(skill_entry.get("tools", []))
        if not requested:
            return set()

        allowed: set[str] = set()
        for name in requested:
            if name == "mcp":
                allowed.update(tool_name for tool_name in available if tool_name.startswith("mcp."))
                continue
            if name in available:
                allowed.add(name)
        return allowed

    def _script_tool_runner(self, allowed_tools: set[str]) -> Callable[[str, dict[str, Any] | None], Any]:
        def run_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
            tool_name = str(name or "").strip()
            if not tool_name:
                raise ValueError("tool name is required")
            if tool_name not in allowed_tools:
                raise PermissionError(f"tool is not allowed for this skill: {tool_name}")
            args = arguments or {}
            if not isinstance(args, dict):
                raise TypeError("tool arguments must be a dict")
            return self.tool_registry.run(tool_name, args)

        return run_tool

    def _run_llm_skill(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str,
    ) -> dict[str, Any]:
        max_steps = int(skill_entry.get("max_steps") or self.config.get("skill_runner", {}).get("max_steps", 8))
        model_overrides = {
            "temperature": float(self.config.get("skill_runner", {}).get("temperature", 0.0)),
            "max_output_tokens": int(self.config.get("skill_runner", {}).get("max_output_tokens", 2048)),
        }
        tools = self._llm_tools(
            skill_entry=skill_entry,
            skill_bundle=skill_bundle,
            user_input=user_input,
            recent_summary=recent_summary,
        )
        tools_by_name = {tool.name: tool for tool in tools}
        model = build_chat_model(
            self.config,
            overrides=model_overrides,
        ).bind_tools(tools)

        messages: list[Any] = [
            SystemMessage(content=SKILL_RUNNER_SYSTEM_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {
                        "skill": _public_skill_payload(skill_entry),
                        "skill_package": skill_bundle,
                        "recent_summary": recent_summary,
                        "user_input": user_input,
                        "available_subagent_tools": sorted(tools_by_name),
                    },
                    ensure_ascii=False,
                )
            ),
        ]

        last_response: Any = None
        tool_events: list[dict[str, Any]] = []
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
                    tool = tools_by_name.get(name)
                    if tool is None:
                        raise KeyError(f"Tool not found: {name}")
                    result = tool.invoke(args)
                except Exception as exc:
                    result = {"error": str(exc), "tool": name}
                tool_events.append({"tool": name, "ok": not (isinstance(result, dict) and result.get("error"))})
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=call_id,
                    )
                )

        output = _extract_text(last_response).strip()
        if not output and isinstance(last_response, AIMessage) and last_response.tool_calls:
            final_model = build_chat_model(self.config, overrides=model_overrides)
            final_response = final_model.invoke(
                [
                    *messages,
                    HumanMessage(
                        content=(
                            "Tool step budget has ended. Read the skill package, references, and tool observations, "
                            "then produce the best final task result without calling more tools."
                        )
                    ),
                ]
            )
            output = _extract_text(final_response).strip()
        return {
            "handled": bool(output),
            "mode": "llm",
            "skill_id": str(skill_entry.get("id", "") or ""),
            "output": output,
            "tool_events": tool_events,
        }

    def _llm_tools(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str,
    ) -> list[BaseTool]:
        if str(skill_entry.get("entry", "") or "").strip():
            return [
                self._script_entry_tool(
                    skill_entry=skill_entry,
                    skill_bundle=skill_bundle,
                    user_input=user_input,
                    recent_summary=recent_summary,
                )
            ]
        return list(self.tool_registry.tools())

    def _script_entry_tool(
        self,
        *,
        skill_entry: dict[str, Any],
        skill_bundle: str,
        user_input: str,
        recent_summary: str,
    ) -> BaseTool:
        entry = str(skill_entry.get("entry", "") or "").strip()

        def run_skill_script(task: str = "") -> dict[str, Any]:
            """Run the selected skill package's Python entry script after reading the skill instructions."""

            task_text = str(task or "").strip() or user_input
            return self._run_script_entry(
                skill_entry=skill_entry,
                skill_bundle=skill_bundle,
                user_input=task_text,
                recent_summary=recent_summary,
            )

        return StructuredTool.from_function(
            func=run_skill_script,
            name=RUN_SKILL_SCRIPT_TOOL_NAME,
            description=(
                "Run this skill package's executable Python script entry after you have read SKILL.md and references. "
                "Use it when the skill instructions indicate that deterministic script execution is useful. "
                f"Entry: {entry}. Pass a concise task string."
            ),
        )


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
        "entry": str(skill_entry.get("entry", "") or ""),
        "has_script": bool(str(skill_entry.get("entry", "") or "").strip()),
    }


def _extract_text(response: Any) -> str:
    if response is None:
        return ""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    return [str(item).strip() for item in items if str(item or "").strip()]
