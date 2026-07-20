from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Run static asakud-agent evaluation checks.")
    parser.add_argument("--strict-models", action="store_true", help="Fail if model api_key/base_url are empty.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results = run_checks(strict_models=args.strict_models)
    if args.json:
        print(json.dumps([item.__dict__ for item in results], ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"{item.status.upper():5} {item.name}: {item.message}")

    return 1 if any(item.status == "fail" for item in results) else 0


def run_checks(*, strict_models: bool) -> list[CheckResult]:
    from agent_loop.config_loader import load_config, project_path
    from agent_loop.nodes.skills import load_skill_registry
    from prompts.system import build_hot_memory_system_prompt, build_static_system_prompt
    from tools.registry import ToolRegistry

    config = load_config()
    checks: list[CheckResult] = []
    checks.extend(_check_model_roles(config, strict_models=strict_models))
    checks.extend(_check_memory_files(config, project_path))
    checks.extend(_check_tool_registry(config, ToolRegistry))
    checks.extend(_check_skill_registry(config, load_skill_registry, project_path))
    checks.extend(_check_style_registry(config, project_path))
    checks.extend(_check_db_schema(config, project_path))
    checks.extend(_check_prompt_contract(config, build_static_system_prompt, build_hot_memory_system_prompt))
    return checks


def _check_model_roles(config: dict[str, Any], *, strict_models: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    expected = ("main_model", "route_model", "multimodal_model")
    for key in expected:
        model = config.get(key)
        if not isinstance(model, dict):
            results.append(CheckResult(f"model.{key}", "fail", "missing model role"))
            continue
        missing = [field for field in ("name", "base_url", "api_key") if not str(model.get(field, "") or "").strip()]
        if missing and strict_models:
            results.append(CheckResult(f"model.{key}", "fail", f"missing required fields: {missing}"))
        elif missing:
            results.append(CheckResult(f"model.{key}", "warn", f"not runnable until dashboard fills: {missing}"))
        else:
            results.append(CheckResult(f"model.{key}", "pass", str(model.get("name", ""))))
    if "model" in config:
        results.append(CheckResult("model.legacy", "warn", "legacy top-level model key still exists"))
    else:
        results.append(CheckResult("model.legacy", "pass", "only three model roles are configured"))
    return results


def _check_memory_files(config: dict[str, Any], project_path) -> list[CheckResult]:  # noqa: ANN001
    results: list[CheckResult] = []
    memory_files = config.get("memory", {}).get("markdown_files", [])
    expected_ids = {"memory", "self", "pending", "core"}
    actual_ids = {str(item.get("id", "") or "") for item in memory_files if isinstance(item, dict)}
    missing_ids = sorted(expected_ids - actual_ids)
    extra_ids = sorted(actual_ids - expected_ids)
    if missing_ids:
        results.append(CheckResult("memory.registry", "fail", f"missing ids: {missing_ids}"))
    elif extra_ids:
        results.append(CheckResult("memory.registry", "warn", f"unexpected ids: {extra_ids}"))
    else:
        results.append(CheckResult("memory.registry", "pass", "cold memory ids are non-overlapping"))

    for item in memory_files:
        if not isinstance(item, dict):
            continue
        memory_id = str(item.get("id", "") or "")
        path = project_path(str(item.get("path", "") or ""))
        status = "pass" if path.exists() else "fail"
        results.append(CheckResult(f"memory.file.{memory_id}", status, str(path)))

    recent_summary_path = project_path(config.get("recent_summary", {}).get("path", "memory/RECENT_SUMMARY.md"))
    results.append(
        CheckResult(
            "memory.recent_summary",
            "pass" if recent_summary_path.exists() else "fail",
            str(recent_summary_path),
        )
    )

    removed_files = ["memory/HISTORY.md", "memory/NOW.md", "memory/SCHEDULED_TASKS.md"]
    for relative in removed_files:
        path = project_path(relative)
        results.append(
            CheckResult(
                f"memory.removed.{Path(relative).stem.lower()}",
                "fail" if path.exists() else "pass",
                "removed" if not path.exists() else f"still exists: {path}",
            )
        )
    return results


def _check_tool_registry(config: dict[str, Any], tool_registry_cls) -> list[CheckResult]:  # noqa: ANN001
    registry = tool_registry_cls(config.get("tools", {}).get("enabled"), config=config)
    names = registry.names()
    results = [CheckResult("tools.registry", "pass" if names else "fail", ", ".join(names) or "empty")]
    for required in ("fetch_web", "create_reminder", "list_reminders", "cancel_reminder"):
        results.append(
            CheckResult(
                f"tools.{required}",
                "pass" if required in names else "fail",
                "registered" if required in names else "missing",
            )
        )
    return results


def _check_skill_registry(config: dict[str, Any], load_skill_registry, project_path) -> list[CheckResult]:  # noqa: ANN001
    results: list[CheckResult] = []
    skills = load_skill_registry(config)
    results.append(CheckResult("skills.registry", "pass", f"{len(skills)} loadable skill entries"))
    for item in skills:
        skill_id = str(item.get("id", "") or "")
        path = project_path(str(item.get("path", "") or ""))
        status = "pass" if path.exists() else "fail"
        results.append(CheckResult(f"skills.{skill_id}.path", status, str(path)))
        if "enabled" not in item:
            results.append(CheckResult(f"skills.{skill_id}.enabled", "warn", "enabled defaults to true"))
    return results


def _check_style_registry(config: dict[str, Any], project_path) -> list[CheckResult]:  # noqa: ANN001
    path = project_path(config.get("paths", {}).get("style_config_file", "styles/style.config.md"))
    if not path.exists():
        return [CheckResult("styles.registry", "fail", str(path))]
    data = _parse_markdown_json(path.read_text(encoding="utf-8"))
    styles = data.get("styles", []) if isinstance(data, dict) else []
    if not isinstance(styles, list):
        return [CheckResult("styles.registry", "fail", "styles must be a list")]
    results = [CheckResult("styles.registry", "pass", f"{len(styles)} style entries")]
    for item in styles:
        if not isinstance(item, dict):
            continue
        style_id = str(item.get("id", "") or "")
        if str(item.get("source", "") or "") == "guide":
            guide = str(item.get("guide", "") or "").strip()
            results.append(
                CheckResult(
                    f"styles.{style_id}.guide",
                    "pass" if guide else "fail",
                    "inline style guide" if guide else "guide source requires guide text",
                )
            )
            continue
        style_path = project_path(str(item.get("path", "") or ""))
        results.append(
            CheckResult(
                f"styles.{style_id}.path",
                "pass" if style_path.exists() else "fail",
                str(style_path),
            )
        )
    return results


def _check_db_schema(config: dict[str, Any], project_path) -> list[CheckResult]:  # noqa: ANN001
    schema_path = project_path(config.get("paths", {}).get("schema", "db/session_memory.schema.sql"))
    if not schema_path.exists():
        return [CheckResult("db.schema", "fail", str(schema_path))]
    sql = schema_path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="asakud-static-eval-") as temp_dir:
        database_path = Path(temp_dir) / "session_memory.db"
        conn = sqlite3.connect(database_path)
        try:
            conn.executescript(sql)
            table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        finally:
            conn.close()
    tables = {str(row[0]) for row in table_rows}
    required = {"sessions", "messages", "memory_events", "web_crawls", "reminders", "reminder_runs"}
    missing = sorted(required - tables)
    return [
        CheckResult(
            "db.schema",
            "fail" if missing else "pass",
            f"missing tables: {missing}" if missing else f"tables={sorted(tables)}",
        )
    ]


def _check_prompt_contract(config: dict[str, Any], build_static, build_hot) -> list[CheckResult]:  # noqa: ANN001
    static_prompt = build_static(
        config=config,
        tool_names=["fetch_web", "create_reminder", "run_skill"],
        markdown_memory={
            "self": "- [modified_at=2026-07-19] prefer concise replies",
            "memory": "- [modified_at=2026-07-19] user is building asakud-agent",
            "core": "- [modified_at=2026-07-18] archived stable fact",
        },
    )
    hot_prompt = build_hot({"self": ["temporary tone update"], "memory": ["pending stable fact"]})
    checks = [
        CheckResult(
            "prompt.static.cold_memory",
            "pass" if all(token in static_prompt for token in ("[self]", "[memory]", "[core]")) else "fail",
            "static prompt includes cold memory sections",
        ),
        CheckResult(
            "prompt.dynamic.hot_memory",
            "pass" if "Hot Redis memory updates" in hot_prompt else "fail",
            "dynamic prompt includes Redis hot memory only when present",
        ),
        CheckResult(
            "prompt.skill_not_injected",
            "pass" if "B3" not in static_prompt and "SKILL.md" not in static_prompt else "warn",
            "skills should run through run_skill, not be injected into the main system prompt",
        ),
    ]
    return checks


def _parse_markdown_json(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    raw = match.group(1) if match else text
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
