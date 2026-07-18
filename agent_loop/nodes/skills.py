from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool, StructuredTool

from compact import load_recent_summary
from skill_runner import SkillRunnerAgent

from ..background import enqueue_skill_build
from ..config_loader import load_config, project_path
from llm.factory import build_route_model
from prompts.skills import SKILL_ROUTER_PROMPT

SKILL_CONFIG_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
GENERATED_SKILL_DIR = "generated"
RUN_SKILL_TOOL_NAME = "run_skill"
ALLOWED_REFERENCE_SUFFIXES = {".md", ".txt", ".json"}
ALLOWED_SCRIPT_SUFFIXES = {".py"}
BLOCKED_SCRIPT_PATTERNS = (
    "subprocess",
    "os.system",
    "eval(",
    "exec(",
    "__import__",
    "socket",
    "requests.",
    "urllib.request",
    "shutil.rmtree",
    "Remove-Item",
)


def build_skill_runner_tool(config: dict | None = None) -> BaseTool | None:
    cfg = config or load_config()
    registry = load_runtime_skill_registry(cfg)
    if not registry:
        return None

    runner = SkillRunnerAgent(cfg)
    available_skills = "\n".join(
        f"- {item['id']}: {item['summary']}" for item in registry if item.get("id") and item.get("summary")
    )

    def _run_skill(skill_id: str, task: str) -> dict[str, Any]:
        """Run one executable skill package by id and return its task result."""

        normalized_id = _normalize_skill_id(str(skill_id or ""))
        task_text = str(task or "").strip()
        if not normalized_id:
            return {
                "handled": False,
                "error": "skill_id is required",
                "available_skills": [_public_skill_summary(item) for item in registry],
            }
        if not task_text:
            return {"handled": False, "skill_id": normalized_id, "error": "task is required"}

        entry = _skill_by_id(registry, normalized_id)
        if entry is None:
            return {
                "handled": False,
                "skill_id": normalized_id,
                "error": f"unknown skill_id: {normalized_id}",
                "available_skills": [_public_skill_summary(item) for item in registry],
            }

        skill_bundle = load_skill_bundle(cfg, normalized_id, registry=registry)
        if not skill_bundle:
            return {"handled": False, "skill_id": normalized_id, "error": "skill bundle is empty or missing"}

        result = runner.run(
            skill_entry=entry,
            skill_bundle=skill_bundle,
            user_input=task_text,
            recent_summary=load_recent_summary(cfg),
        )
        return {
            "action": RUN_SKILL_TOOL_NAME,
            "skill_id": normalized_id,
            **result,
        }

    return StructuredTool.from_function(
        func=_run_skill,
        name=RUN_SKILL_TOOL_NAME,
        description=(
            "Run one executable skill package by id. Use this when the user's task matches a listed skill. "
            "You may call this tool multiple times when a task genuinely needs multiple skills, then combine "
            "the returned results yourself before final answering. For scripted skills, the skill sub-agent "
            "first reads SKILL.md and references, then decides whether to call the script; any fetch_web/MCP "
            "calls are owned by that script through its runtime context. For non-script skills, the sub-agent "
            "may use enabled project tools directly when the skill package requires external information.\n\n"
            f"Available executable skills:\n{available_skills}"
        ),
    )


def get_skill_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 250})
    runner = SkillRunnerAgent(cfg)

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        selected_ids, normalized_input, registry = resolve_skill_ids(state=state, route_llm=route_llm, config=cfg)
        _update_user_input(state, normalized_input)

        memory = dict(state.get("memory", {}) or {})
        memory["skill_ids"] = selected_ids
        memory["skill_registry"] = [_public_skill_summary(item) for item in registry]
        memory["skill_runner"] = {"handled": False}

        if selected_ids:
            selected_id = selected_ids[0]
            entry = _skill_by_id(registry, selected_id)
            skill_bundle = load_skill_bundle(cfg, selected_id, registry=registry)
            if entry and skill_bundle:
                result = runner.run(
                    skill_entry=entry,
                    skill_bundle=skill_bundle,
                    user_input=normalized_input,
                    recent_summary=load_recent_summary(cfg),
                )
                memory["skill_runner"] = result
                if result.get("handled") and str(result.get("output", "") or "").strip():
                    state["assistant_output"] = str(result.get("output", "") or "").strip()

        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def get_save_skill_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        original_user_input = str(state.get("original_user_input", state.get("user_input", "")) or "")
        normalized_user_input = str(state.get("user_input", "") or "")
        assistant_output = str(state.get("assistant_output", "") or "")
        memory = dict(state.get("memory", {}) or {})
        skill_runner = memory.get("skill_runner", {})
        skill_runs = list(memory.get("skill_runs", []) or [])

        if not original_user_input or not assistant_output:
            return state
        if isinstance(skill_runner, dict) and skill_runner.get("handled"):
            return state
        if any(isinstance(item, dict) and item.get("handled") for item in skill_runs):
            return state
        if len(original_user_input) + len(assistant_output) < 120:
            return state

        memory["skill_builder"] = enqueue_skill_build(
            cfg,
            {
                "original_user_input": original_user_input,
                "normalized_user_input": normalized_user_input,
                "assistant_output": assistant_output,
            },
        )
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def load_skill_registry(config: dict[str, Any]) -> list[dict[str, Any]]:
    registry_path = _skill_config_path(config)
    if not registry_path.exists():
        return []

    text = registry_path.read_text(encoding="utf-8")
    data = _parse_registry_text(text, registry_path.suffix.lower())
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        return []

    result: list[dict[str, Any]] = []
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
        entry: dict[str, Any] = {
            "id": skill_id,
            "summary": summary,
            "path": path,
            "type": str(item.get("type", "workflow") or "workflow").strip(),
        }
        for key in ("entry", "tools", "references", "max_steps"):
            if key in item:
                entry[key] = item[key]
        result.append(entry)
    return result


def write_skill_registry(config: dict[str, Any], skills: list[dict[str, Any]]) -> None:
    registry_path = _skill_config_path(config)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"skills": [_registry_entry_payload(item) for item in skills if _is_valid_registry_entry(item)]}
    content = "# Skill Registry\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n"
    registry_path.write_text(content, encoding="utf-8")


def resolve_skill_ids(
    state: dict[str, Any],
    route_llm: Runnable | None,
    config: dict[str, Any],
) -> tuple[list[str], str, list[dict[str, Any]]]:
    content = str(state.get("user_input", "") or "")
    registry = load_runtime_skill_registry(config)
    if not registry:
        return [], content, []

    normalized_input = content.strip()
    routed_ids = route_skill_ids(content=normalized_input, route_llm=route_llm, registry=registry)
    return _dedupe(routed_ids)[:1], normalized_input, registry


def route_skill_ids(content: str, route_llm: Runnable | None, registry: list[dict[str, Any]]) -> list[str]:
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
    registry: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    items = registry or load_skill_registry(config)
    by_id = {item["id"]: item for item in items}
    result: dict[str, str] = {}

    for skill_id in skill_ids:
        entry = by_id.get(skill_id)
        if not entry:
            continue
        entry_path = project_path(entry["path"])
        bundle = _load_skill_bundle(entry_path, entry)
        if bundle:
            result[skill_id] = bundle
    return result


def load_skill_bundle(
    config: dict[str, Any],
    skill_id: str,
    registry: list[dict[str, Any]] | None = None,
) -> str:
    entry = _skill_by_id(registry or load_skill_registry(config), skill_id)
    if not entry:
        return ""
    return _load_skill_bundle(project_path(entry["path"]), entry)


def persist_generated_skill(
    config: dict[str, Any],
    payload: dict[str, Any],
    existing_registry: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not bool(payload.get("save_skill", False)):
        return {}

    skill_id = _normalize_skill_id(str(payload.get("id", "") or ""))
    summary = str(payload.get("summary", "") or "").strip()
    skill_markdown = str(payload.get("skill_markdown", "") or payload.get("content_markdown", "") or "").strip()
    if not skill_id or not summary or not skill_markdown:
        return {}

    registry = list(existing_registry or load_skill_registry(config))
    existing_ids = {item["id"] for item in registry}
    final_id = _choose_generated_skill_id(skill_id, existing_ids)

    skills_root = project_path(config.get("paths", {}).get("skills_dir", "skills"))
    skill_dir = skills_root / GENERATED_SKILL_DIR / final_id
    created_dir = not skill_dir.exists()
    registry_entry: dict[str, Any] = {}

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)

        references = _normalize_generated_files(
            payload.get("references", []),
            default_dir="reference",
            allowed_suffixes=ALLOWED_REFERENCE_SUFFIXES,
        )
        scripts = _normalize_generated_files(
            payload.get("scripts", []),
            default_dir="scripts",
            allowed_suffixes=ALLOWED_SCRIPT_SUFFIXES,
        )
        scripts = [item for item in scripts if _script_is_safe(item["content"])]
        entry_text = _normalize_entry(str(payload.get("entry", "") or ""), scripts)
        if entry_text and not _entry_script_is_available(entry_text, scripts):
            entry_text = ""

        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(_normalize_skill_body(final_id, skill_markdown), encoding="utf-8")

        for item in references + scripts:
            target = skill_dir / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item["content"].rstrip() + "\n", encoding="utf-8")

        for item in scripts:
            compile(item["content"], item["path"], "exec")

        reference_paths = [item["path"] for item in references if item["path"].endswith((".md", ".txt"))]
        registry_entry = {
            "id": final_id,
            "summary": summary,
            "path": _registry_path(skill_path),
            "type": str(payload.get("type", "workflow") or "workflow").strip() or "workflow",
        }
        tools = _allowed_skill_tools(config, payload.get("tools", []))
        max_steps = _positive_int(payload.get("max_steps"), default=8)
        if tools:
            registry_entry["tools"] = tools
        if reference_paths:
            registry_entry["references"] = reference_paths
        if max_steps:
            registry_entry["max_steps"] = max_steps
        if entry_text:
            registry_entry["entry"] = entry_text

        metadata = {
            "id": final_id,
            "summary": summary,
            "type": registry_entry["type"],
            "tools": registry_entry.get("tools", []),
            "entry": registry_entry.get("entry", ""),
            "references": registry_entry.get("references", []),
            "max_steps": registry_entry.get("max_steps", 8),
            "generated": True,
        }
        (skill_dir / "skill.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        registry.append(registry_entry)
        write_skill_registry(config, registry)
        return registry_entry
    except Exception:
        if created_dir and skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        return {}


def _skill_config_path(config: dict[str, Any]) -> Path:
    path_value = config.get("paths", {}).get("skill_config_file", "skills/skill.config.md")
    return project_path(path_value)


def load_runtime_skill_registry(config: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
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


def _load_skill_bundle(entry_path: Path, entry: dict[str, Any] | None = None) -> str:
    if not entry_path.exists():
        return ""

    root = entry_path.parent
    bundle_paths = _bundle_paths(root, entry_path, entry or {})
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


def _bundle_paths(root: Path, entry_path: Path, entry: dict[str, Any]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path.exists() and path.suffix.lower() in ALLOWED_REFERENCE_SUFFIXES and path.name != "README.md" and path not in seen:
            seen.add(path)
            ordered.append(path)

    add(entry_path)
    add(root / "soul.md")
    add(root / "limit.md")

    for reference in _string_list(entry.get("references", [])):
        add(root / reference)

    for directory_name in ("reference", "resource"):
        reference_dir = root / directory_name
        if reference_dir.exists():
            for path in sorted(reference_dir.rglob("*")):
                if path.is_file():
                    add(path)
    return ordered


def _normalize_generated_files(
    value: Any,
    *,
    default_dir: str,
    allowed_suffixes: set[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value[:8], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "") or "").strip()
        if not content:
            continue
        raw_path = str(item.get("path", "") or "").strip()
        if not raw_path:
            suffix = ".py" if ".py" in allowed_suffixes else ".md"
            raw_path = f"{default_dir}/item-{index}{suffix}"
        safe_path = _safe_relative_path(raw_path, allowed_suffixes)
        if not safe_path or safe_path in seen:
            continue
        seen.add(safe_path)
        normalized.append({"path": safe_path, "content": content})
    return normalized


def _safe_relative_path(raw_path: str, allowed_suffixes: set[str]) -> str:
    candidate = raw_path.replace("\\", "/").strip().lstrip("/")
    if not candidate or re.match(r"^[a-zA-Z]:", candidate):
        return ""
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts:
        return ""
    suffix = path.suffix.lower()
    if suffix not in allowed_suffixes:
        return ""
    parts = [part for part in path.parts if part not in ("", ".")]
    if not parts:
        return ""
    if len(parts) == 1 and parts[0].lower() in {"skill.md", "skill.json", "readme.md"}:
        return ""
    return str(PurePosixPath(*parts))


def _registry_path(path: Path) -> str:
    root = project_path(".").resolve()
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _script_is_safe(content: str) -> bool:
    lowered = content.lower()
    if any(pattern.lower() in lowered for pattern in BLOCKED_SCRIPT_PATTERNS):
        return False
    try:
        compile(content, "<generated_skill_script>", "exec")
    except SyntaxError:
        return False
    return True


def _normalize_entry(entry: str, scripts: list[dict[str, str]]) -> str:
    text = entry.strip().replace("\\", "/")
    if not text and len(scripts) == 1 and re.search(r"def\s+run\s*\(", scripts[0]["content"]):
        return f"{scripts[0]['path']}:run"
    if ":" not in text:
        return ""
    path_text, function_name = text.split(":", 1)
    safe_path = _safe_relative_path(path_text, ALLOWED_SCRIPT_SUFFIXES)
    function_name = function_name.strip()
    if not safe_path or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", function_name):
        return ""
    return f"{safe_path}:{function_name}"


def _entry_script_is_available(entry: str, scripts: list[dict[str, str]]) -> bool:
    path_text, function_name = entry.split(":", 1)
    for item in scripts:
        if item["path"] != path_text:
            continue
        return bool(re.search(rf"def\s+{re.escape(function_name)}\s*\(", item["content"]))
    return False


def _allowed_skill_tools(config: dict[str, Any], value: Any) -> list[str]:
    enabled = set(_string_list(config.get("tools", {}).get("enabled", [])))
    requested = _string_list(value)
    if not enabled:
        return []
    return [tool for tool in requested if tool in enabled]


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _skill_by_id(registry: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    normalized = _normalize_skill_id(skill_id)
    for item in registry:
        if item.get("id") == normalized:
            return item
    return None


def _is_valid_registry_entry(item: dict[str, Any]) -> bool:
    return bool(
        str(item.get("id", "") or "").strip()
        and str(item.get("summary", "") or "").strip()
        and str(item.get("path", "") or "").strip()
    )


def _registry_entry_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": _normalize_skill_id(str(item.get("id", "") or "")),
        "summary": str(item.get("summary", "") or "").strip(),
        "path": str(item.get("path", "") or "").strip(),
        "type": str(item.get("type", "workflow") or "workflow").strip(),
    }
    for key in ("entry", "tools", "references", "max_steps"):
        if key in item and item[key] not in ("", None, [], {}):
            payload[key] = item[key]
    return payload


def _public_skill_summary(item: dict[str, Any]) -> dict[str, str]:
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


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
