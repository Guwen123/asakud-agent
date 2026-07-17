from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from style_runner import StyleRunnerAgent

from ..config_loader import load_config


def get_style_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    style_cfg = cfg.get("style", {})
    runner = StyleRunnerAgent(cfg)

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        if not bool(style_cfg.get("enabled", True)):
            return state

        draft = str(state.get("assistant_output", "") or "").strip()
        if not draft:
            return state

        style_name = _selected_style_name(state, style_cfg)
        result = runner.run(
            draft_answer=draft,
            user_input=str(state.get("original_user_input", state.get("user_input", "")) or ""),
            style_name=style_name,
        )
        styled = str(result.get("output", "") or "").strip()
        if not styled:
            return state

        memory = dict(state.get("memory", {}) or {})
        memory["style"] = {
            "name": style_name,
            "applied": bool(result.get("handled")),
            "source": result.get("source", {}),
            "error": str(result.get("error", "") or ""),
        }
        state["memory"] = memory
        state["assistant_output"] = styled
        return state

    return RunnableLambda(_run)


def _selected_style_name(state: dict[str, Any], style_cfg: dict[str, Any]) -> str:
    memory = dict(state.get("memory", {}) or {})
    explicit = str(memory.get("style_name", "") or state.get("style_name", "") or "").strip().lower()
    if explicit:
        return explicit
    return str(style_cfg.get("default", "atri") or "atri").strip().lower()
