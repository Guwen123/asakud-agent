from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_loop.models.factory import build_chat_model
from prompts.skills import SKILL_SAVE_PROMPT


class SkillBuilderWorker:
    """Background sub-agent that turns successful interactions into reusable skills."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def process(self, job: Any) -> None:
        if job.kind != "skill_build":
            return
        payload = job.payload
        original_user_input = str(payload.get("original_user_input", "") or "")
        normalized_user_input = str(payload.get("normalized_user_input", "") or "")
        assistant_output = str(payload.get("assistant_output", "") or "")
        if not original_user_input or not assistant_output:
            return

        from agent_loop.nodes.skills import _public_skill_summary, load_skill_registry, persist_generated_skill

        registry = load_skill_registry(self.config)
        builder_config = self.config.get("skill_builder", {})
        model = build_chat_model(
            self.config,
            overrides={
                "temperature": float(builder_config.get("temperature", 0.0)),
                "max_output_tokens": int(builder_config.get("max_output_tokens", 4096)),
            },
        )
        response = model.invoke(
            [
                SystemMessage(content=SKILL_SAVE_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "original_user_input": original_user_input,
                            "normalized_user_input": normalized_user_input,
                            "assistant_output": assistant_output,
                            "existing_skills": [_public_skill_summary(item) for item in registry],
                            "enabled_tools": _enabled_tools(self.config),
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        skill_payload = _parse_json(_extract_text(response))
        persist_generated_skill(self.config, skill_payload, existing_registry=registry)


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


def _enabled_tools(config: dict[str, Any]) -> list[str]:
    tools = config.get("tools", {}).get("enabled", [])
    if not isinstance(tools, list):
        return []
    return [str(item) for item in tools if str(item or "").strip()]
