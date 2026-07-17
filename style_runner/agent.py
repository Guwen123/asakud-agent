from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_loop.config_loader import project_path
from agent_loop.models.factory import build_chat_model
from prompts.style import STYLE_REWRITE_PROMPT


DEFAULT_ATRI_STYLE_SKILL = "styles/atri/SKILL.md"
STYLE_CONFIG_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class StyleRunnerAgent:
    """Small style-only sub-agent that rewrites drafts using a style SKILL.md."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        style_cfg = config.get("style", {})
        self.model = build_chat_model(
            config,
            overrides={
                "temperature": float(style_cfg.get("temperature", 0.0)),
                "max_output_tokens": int(style_cfg.get("max_output_tokens", 2048)),
            },
        )

    def run(self, *, draft_answer: str, user_input: str, style_name: str) -> dict[str, Any]:
        draft = str(draft_answer or "").strip()
        selected_style = str(style_name or "").strip().lower()
        if not draft:
            return {"handled": False, "style": selected_style, "output": ""}
        if selected_style in {"none", "off"}:
            return {"handled": False, "style": selected_style, "output": draft}

        style_skill = self._load_style_skill(selected_style)
        if not style_skill:
            return {
                "handled": False,
                "style": selected_style,
                "output": draft,
                "error": "style skill is empty or missing",
            }

        response = self.model.invoke(
            [
                SystemMessage(
                    content=STYLE_REWRITE_PROMPT.format(
                        style_name=selected_style,
                        style_skill=style_skill,
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "user_input": str(user_input or ""),
                            "draft_answer": draft,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        output = _extract_text(response).strip()
        return {
            "handled": bool(output),
            "style": selected_style,
            "output": output or draft,
            "source": self._style_source(selected_style),
        }

    def _load_style_skill(self, style_name: str) -> str:
        source = self._style_source(style_name)
        if source.get("type") == "guide":
            return str(source.get("content", "") or "").strip()

        path_text = str(source.get("path", "") or "").strip()
        if not path_text:
            return ""
        path = project_path(path_text)
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _style_source(self, style_name: str) -> dict[str, str]:
        registry_item = _style_registry_item(self.config, style_name)
        if registry_item:
            guide = str(registry_item.get("guide", "") or "").strip()
            if guide:
                return {"type": "guide", "content": guide, "style_type": str(registry_item.get("type", "") or "")}
            path = str(registry_item.get("path", "") or registry_item.get("skill_path", "") or "").strip()
            if path:
                return {"type": "skill", "path": path, "style_type": str(registry_item.get("type", "") or "")}

        styles = self.config.get("style", {}).get("styles", {})
        style_item = styles.get(style_name, {}) if isinstance(styles, dict) else {}
        if isinstance(style_item, dict):
            skill_path = str(style_item.get("skill_path", "") or "").strip()
            if skill_path:
                return {"type": "skill", "path": skill_path}
            guide = str(style_item.get("guide", "") or "").strip()
            if guide:
                return {"type": "guide", "content": guide}

        if style_name == "atri":
            return {"type": "skill", "path": DEFAULT_ATRI_STYLE_SKILL}
        return {}


def _style_registry_item(config: dict[str, Any], style_name: str) -> dict[str, Any]:
    registry = _load_style_registry(config)
    normalized = _normalize_id(style_name)
    for item in registry.get("styles", []):
        if not isinstance(item, dict):
            continue
        if _normalize_id(str(item.get("id", "") or "")) == normalized:
            return item
    return {}


def _load_style_registry(config: dict[str, Any]) -> dict[str, Any]:
    path_value = config.get("paths", {}).get("style_config_file", "styles/style.config.md")
    path = project_path(path_value)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    match = STYLE_CONFIG_PATTERN.search(text)
    raw = match.group(1) if match else text
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_id(value: str) -> str:
    lowered = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    return re.sub(r"-{2,}", "-", normalized).strip("-")


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)
