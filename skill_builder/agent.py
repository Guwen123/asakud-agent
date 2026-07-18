from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_loop.config_loader import project_path
from llm.factory import build_chat_model
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
                            "skill_templates": _load_skill_templates(self.config),
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


def _load_skill_templates(config: dict[str, Any]) -> list[dict[str, Any]]:
    builder_config = config.get("skill_builder", {})
    templates_dir = project_path(str(builder_config.get("templates_dir", "skills/_templates") or "skills/_templates"))
    if not templates_dir.exists() or not templates_dir.is_dir():
        return []

    max_chars = _safe_int(builder_config.get("max_template_chars"), 6000)
    templates: list[dict[str, Any]] = []
    for item in sorted(templates_dir.iterdir()):
        if not item.is_dir():
            continue
        template = _read_template(item, max_chars=max_chars)
        if template:
            templates.append(template)
    return templates


def _read_template(root: Path, *, max_chars: int) -> dict[str, Any]:
    skill_path = root / "SKILL.md"
    metadata_path = root / "skill.json"
    if not skill_path.exists():
        return {}

    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                metadata = raw
        except json.JSONDecodeError:
            metadata = {}

    files: dict[str, str] = {}
    for path in _template_files(root):
        relative = str(path.relative_to(root)).replace("\\", "/")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        files[relative] = _truncate(text, max_chars)

    return {
        "id": str(metadata.get("id", root.name) or root.name),
        "summary": str(metadata.get("summary", "") or ""),
        "tools": metadata.get("tools", []),
        "entry": str(metadata.get("entry", "") or ""),
        "references": metadata.get("references", []),
        "files": files,
    }


def _template_files(root: Path) -> list[Path]:
    allowed_suffixes = {".md", ".json", ".py", ".txt"}
    ignored_dirs = {"__pycache__"}
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        result.append(path)
    return result


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(max_chars - 3, 0)].rstrip() + "..."


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
