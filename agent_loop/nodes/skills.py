from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from ..config_loader import load_config, project_path
from ..models.factory import build_chat_model, build_route_model
from ..prompts import SKILL_ROUTER_PROMPT, SKILL_SAVE_PROMPT

SKILL_CONFIG_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
GENERATED_SKILL_DIR = "generated"
ATRI_SKILL_ID = "atri-roleplay"
ATRI_SKILL_PATH = "skills/atri-roleplay/SKILL.md"


def get_skill_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 250})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        selected_ids, normalized_input, registry = resolve_skill_ids(state=state, route_llm=route_llm, config=cfg)
        _update_user_input(state, normalized_input)

        skill_texts = load_skill_texts(cfg, selected_ids, registry=registry)
        memory = dict(state.get("memory", {}) or {})
        memory["skills"] = skill_texts
        memory["skill_ids"] = selected_ids
        memory["skill_registry"] = [_public_skill_summary(item) for item in registry]
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def get_save_skill_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    chat_model = build_chat_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 900})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        original_user_input = str(state.get("original_user_input", state.get("user_input", "")) or "")
        normalized_user_input = str(state.get("user_input", "") or "")
        assistant_output = str(state.get("assistant_output", "") or "")
        memory = dict(state.get("memory", {}) or {})
        loaded_skill_ids = list(memory.get("skill_ids", []))
        non_base_skill_ids = [skill_id for skill_id in loaded_skill_ids if skill_id != "atri-roleplay"]

        if not original_user_input or not assistant_output:
            return state
        if non_base_skill_ids:
            return state
        if len(original_user_input) + len(assistant_output) < 120:
            return state

        registry = load_skill_registry(cfg)
        response = chat_model.invoke(
            [
                SystemMessage(content=SKILL_SAVE_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "original_user_input": original_user_input,
                            "normalized_user_input": normalized_user_input,
                            "assistant_output": assistant_output,
                            "existing_skills": [_public_skill_summary(item) for item in registry],
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        payload = _parse_json(_extract_text(response))
        saved_skill = persist_generated_skill(cfg, payload, existing_registry=registry)
        if saved_skill:
            memory["saved_skill"] = saved_skill
            state["memory"] = memory
        return state

    return RunnableLambda(_run)


def load_skill_registry(config: dict[str, Any]) -> list[dict[str, str]]:
    registry_path = _skill_config_path(config)
    if not registry_path.exists():
        return []

    text = registry_path.read_text(encoding="utf-8")
    data = _parse_registry_text(text, registry_path.suffix.lower())
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        return []

    result: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in skills:
        if not isinstance(item, dict):
            continue
        skill_id = _normalize_skill_id(str(item.get("id", "") or ""))
        summary = str(item.get("summary", "") or "").strip()
        path = str(item.get("path", "") or "").strip()
        if not skill_id or not summary or not path or skill_id in seen_ids:
            continue
        seen_ids.add(skill_id)
        result.append({"id": skill_id, "summary": summary, "path": path})
    return result


def write_skill_registry(config: dict[str, Any], skills: list[dict[str, str]]) -> None:
    registry_path = _skill_config_path(config)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "skills": [
            {
                "id": _normalize_skill_id(str(item.get("id", "") or "")),
                "summary": str(item.get("summary", "") or "").strip(),
                "path": str(item.get("path", "") or "").strip(),
            }
            for item in skills
            if str(item.get("id", "") or "").strip()
            and str(item.get("summary", "") or "").strip()
            and str(item.get("path", "") or "").strip()
        ]
    }
    content = "# Skill Registry\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n"
    registry_path.write_text(content, encoding="utf-8")


def resolve_skill_ids(
    state: dict[str, Any],
    route_llm: Runnable | None,
    config: dict[str, Any],
) -> tuple[list[str], str, list[dict[str, str]]]:
    content = str(state.get("user_input", "") or "")
    registry = load_runtime_skill_registry(config)
    if not registry:
        return [], content, []

    normalized_input = content.strip()
    always_loaded_ids = [item["id"] for item in registry if item["id"] == ATRI_SKILL_ID]
    routed_registry = [item for item in registry if item["id"] != ATRI_SKILL_ID]
    routed_ids = route_skill_ids(content=normalized_input, route_llm=route_llm, registry=routed_registry)
    selected_ids = _dedupe(always_loaded_ids + routed_ids)
    return selected_ids[:2], normalized_input, registry


def route_skill_ids(content: str, route_llm: Runnable | None, registry: list[dict[str, str]]) -> list[str]:
    if route_llm is None or not registry:
        return []

    skill_options = [_public_skill_summary(item) for item in registry]
    allowed_ids = [item["id"] for item in skill_options]
    response = route_llm.invoke(
        [
            SystemMessage(content=SKILL_ROUTER_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {
                        "content": content,
                        "allowed_skill_ids": allowed_ids,
                        "skill_options": skill_options,
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )
    payload = _parse_json(_extract_text(response))
    skill_ids = payload.get("skill_ids", [])
    if not isinstance(skill_ids, list):
        return []

    normalized: list[str] = []
    for item in skill_ids:
        if isinstance(item, str) and item in allowed_ids and item not in normalized:
            normalized.append(item)
    return normalized


def load_skill_texts(
    config: dict[str, Any],
    skill_ids: list[str],
    registry: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    items = registry or load_skill_registry(config)
    by_id = {item["id"]: item for item in items}
    result: dict[str, str] = {}

    for skill_id in skill_ids:
        entry = by_id.get(skill_id)
        if not entry:
            continue
        entry_path = project_path(entry["path"])
        bundle = _load_skill_bundle(entry_path)
        if bundle:
            result[skill_id] = bundle
    return result


def persist_generated_skill(
    config: dict[str, Any],
    payload: dict[str, Any],
    existing_registry: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    if not bool(payload.get("save_skill", False)):
        return {}

    skill_id = _normalize_skill_id(str(payload.get("id", "") or ""))
    summary = str(payload.get("summary", "") or "").strip()
    content_markdown = str(payload.get("content_markdown", "") or "").strip()
    if not skill_id or not summary or not content_markdown:
        return {}

    registry = list(existing_registry or load_skill_registry(config))
    existing_ids = {item["id"] for item in registry}
    existing_ids.add(ATRI_SKILL_ID)
    final_id = _choose_generated_skill_id(skill_id, existing_ids)

    skills_root = project_path(config.get("paths", {}).get("skills_dir", "skills"))
    skill_dir = skills_root / GENERATED_SKILL_DIR / final_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(_normalize_skill_body(final_id, content_markdown), encoding="utf-8")

    entry = {
        "id": final_id,
        "summary": summary,
        "path": str(skill_path.relative_to(project_path("."))).replace("\\", "/"),
    }
    registry.append(entry)
    write_skill_registry(config, registry)
    return entry


def _skill_config_path(config: dict[str, Any]) -> Path:
    path_value = config.get("paths", {}).get("skill_config_file", "skills/skill.config.md")
    return project_path(path_value)


def load_runtime_skill_registry(config: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    builtin = _builtin_atri_skill_entry(config)
    if builtin:
        result.append(builtin)

    for item in load_skill_registry(config):
        if item["id"] not in {entry["id"] for entry in result}:
            result.append(item)
    return result


def _parse_registry_text(text: str, suffix: str) -> dict[str, Any]:
    if suffix == ".json":
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    match = SKILL_CONFIG_PATTERN.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _load_skill_bundle(entry_path: Path) -> str:
    if not entry_path.exists():
        return ""

    root = entry_path.parent
    bundle_paths = _bundle_paths(root, entry_path)
    blocks: list[str] = []
    for index, path in enumerate(bundle_paths):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        if index == 0:
            blocks.append(text)
            continue
        relative_name = str(path.relative_to(root)).replace("\\", "/")
        blocks.append(f"## Extra Reference: {relative_name}\n\n{text}")
    return "\n\n".join(blocks).strip()


def _bundle_paths(root: Path, entry_path: Path) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path.exists() and path.suffix.lower() == ".md" and path.name != "README.md" and path not in seen:
            seen.add(path)
            ordered.append(path)

    add(entry_path)
    add(root / "soul.md")
    add(root / "limit.md")

    resource_dir = root / "resource"
    if resource_dir.exists():
        for path in sorted(resource_dir.rglob("*.md")):
            add(path)
    return ordered


def _builtin_atri_skill_entry(config: dict[str, Any]) -> dict[str, str] | None:
    atri_path = project_path(ATRI_SKILL_PATH)
    if not atri_path.exists():
        return None
    return {
        "id": ATRI_SKILL_ID,
        "summary": "内建 ATRI 角色技能，会在每次进入 skill_node 时自动加载。",
        "path": ATRI_SKILL_PATH,
    }


def _public_skill_summary(item: dict[str, str]) -> dict[str, str]:
    return {
        "id": str(item.get("id", "") or "").strip(),
        "summary": str(item.get("summary", "") or "").strip(),
    }


def _choose_generated_skill_id(base_id: str, existing_ids: set[str]) -> str:
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while True:
        candidate = f"{base_id}-{counter}"
        if candidate not in existing_ids:
            return candidate
        counter += 1


def _normalize_skill_body(skill_id: str, body: str) -> str:
    stripped = body.strip()
    if stripped.startswith("#"):
        return stripped + "\n"
    return f"# {skill_id}\n\n{stripped}\n"


def _normalize_skill_id(value: str) -> str:
    lowered = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def _update_user_input(state: dict[str, Any], normalized_input: str) -> None:
    current_input = str(state.get("user_input", "") or "")
    if normalized_input == current_input:
        return

    state["user_input"] = normalized_input
    messages = list(state.get("messages", []))
    if messages and isinstance(messages[-1], HumanMessage):
        messages[-1] = HumanMessage(content=normalized_input)
        state["messages"] = messages


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


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


get_skill_memory_node = get_skill_node
