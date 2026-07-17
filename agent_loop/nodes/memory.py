from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from memory.hot_store import get_hot_store
from memory.markdown import parse_markdown_entries, render_prompt_entries
from memory.router import route_markdown_entry_ids, route_markdown_ids

from ..config_loader import load_config, project_path
from ..models.factory import build_route_model


def get_md_memory_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    route_llm = build_route_model(cfg, overrides={"temperature": 0.0, "max_output_tokens": 350})

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        routing = state.get("routing", {})
        content = str(state.get("user_input", "") or "")
        selected_ids = select_prompt_markdown_ids(
            config=cfg,
            content=content,
            route_llm=route_llm,
            should_route=bool(routing.get("read_md", False)),
        )
        markdown_by_id, entry_ids_by_memory = load_prompt_markdown_entries(
            config=cfg,
            content=content,
            route_llm=route_llm,
            memory_ids=selected_ids,
        )
        hot_updates = load_hot_updates(cfg)
        record_prompt_entry_access(cfg, entry_ids_by_memory)

        memory = state.get("memory", {})
        memory["markdown"] = markdown_by_id
        memory["markdown_ids"] = selected_ids
        memory["markdown_entry_ids"] = entry_ids_by_memory
        memory["hot_updates"] = hot_updates
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def select_prompt_markdown_ids(
    config: dict[str, Any],
    content: str,
    route_llm: Runnable,
    should_route: bool,
) -> list[str]:
    prompt_cfg = config.get("memory", {}).get("prompt", {})
    always_ids = _string_list(prompt_cfg.get("always_markdown_ids", []))
    always_routed_ids = _string_list(prompt_cfg.get("always_routed_markdown_ids", ["self"]))
    routable_ids = _string_list(prompt_cfg.get("routable_markdown_ids", ["memory"]))
    routed_ids: list[str] = []
    if should_route and routable_ids:
        routed_ids = route_markdown_ids(
            content=content,
            route_llm=route_llm,
            config=config,
            candidate_ids=routable_ids,
        )
    return _dedupe(always_ids + always_routed_ids + routed_ids)


def load_prompt_markdown_entries(
    config: dict[str, Any],
    content: str,
    route_llm: Runnable,
    memory_ids: list[str],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    result: dict[str, str] = {}
    entry_ids_by_memory: dict[str, list[str]] = {}
    blocked_ids = {"history", "pending"}
    prompt_cfg = config.get("memory", {}).get("prompt", {})
    always_sections = _section_map(prompt_cfg.get("always_markdown_sections", {"self": ["Core Rules"]}))
    max_entries_by_id = _int_map(prompt_cfg.get("max_markdown_entries_by_id", {"self": 4, "memory": 6}))
    load_all_ids = set(_string_list(prompt_cfg.get("load_all_entries_for_ids", [])))
    default_limit = int(prompt_cfg.get("max_markdown_entries", 6))

    for item in config.get("memory", {}).get("markdown_files", []):
        memory_id = str(item.get("id", "") or "")
        if memory_id in blocked_ids or memory_id not in memory_ids:
            continue
        path = project_path(item["path"])
        if not path.exists():
            continue
        entries = parse_markdown_entries(path.read_text(encoding="utf-8"), memory_id)
        if not entries:
            continue
        if memory_id in load_all_ids:
            rendered = render_prompt_entries(entries)
            if rendered:
                result[memory_id] = rendered
                entry_ids_by_memory[memory_id] = [
                    str(entry.get("entry_id", ""))
                    for entry in entries
                    if str(entry.get("entry_id", ""))
                ]
            continue

        selected_entries: list[dict[str, Any]] = []
        always_for_id = set(always_sections.get(memory_id, []))
        if always_for_id:
            selected_entries.extend(
                entry
                for entry in entries
                if str(entry.get("section", "")) in always_for_id
            )

        selected_entry_ids = {str(entry.get("entry_id", "")) for entry in selected_entries}
        candidate_entries = [
            entry
            for entry in entries
            if str(entry.get("entry_id", "")) not in selected_entry_ids
        ]
        limit = max(max_entries_by_id.get(memory_id, default_limit) - len(selected_entries), 0)
        routed_entry_ids = route_markdown_entry_ids(
            content=content,
            route_llm=route_llm,
            memory_id=memory_id,
            entries=candidate_entries,
            limit=limit,
        )
        routed_set = set(routed_entry_ids)
        selected_entries.extend(
            entry
            for entry in candidate_entries
            if str(entry.get("entry_id", "")) in routed_set
        )

        rendered = render_prompt_entries(selected_entries)
        if not rendered:
            continue
        result[memory_id] = rendered
        entry_ids_by_memory[memory_id] = [
            str(entry.get("entry_id", ""))
            for entry in selected_entries
            if str(entry.get("entry_id", ""))
        ]

    return result, entry_ids_by_memory


def record_prompt_entry_access(config: dict[str, Any], entry_ids_by_memory: dict[str, list[str]]) -> None:
    if not entry_ids_by_memory:
        return
    hot_store = get_hot_store(config)
    if not hot_store.enabled:
        return
    for memory_id, entry_ids in entry_ids_by_memory.items():
        hot_store.record_entry_access(memory_id, entry_ids)


def load_hot_updates(config: dict[str, Any]) -> dict[str, list[str]]:
    memory_cfg = config.get("memory", {})
    prompt_cfg = memory_cfg.get("prompt", {})
    hot_cfg = memory_cfg.get("hot_store", {})
    memory_ids = _string_list(
        prompt_cfg.get(
            "hot_ids",
            hot_cfg.get("prompt_include_ids", ["self", "memory", "pending"]),
        )
    )
    limit = int(prompt_cfg.get("hot_pending_limit", hot_cfg.get("prompt_pending_limit", 8)))
    hot_store = get_hot_store(config)
    pending = hot_store.read_pending(memory_ids, limit=max(limit, 1))
    return {
        memory_id: [_format_hot_update(item) for item in updates if item.content]
        for memory_id, updates in pending.items()
        if updates
    }


def _format_hot_update(item: Any) -> str:
    created_at = getattr(item, "created_at", 0.0)
    content = str(getattr(item, "content", "") or "").strip()
    timestamp = _format_unix_timestamp(created_at)
    if timestamp:
        return f"[{timestamp}] {content}"
    return content


def _format_unix_timestamp(value: Any) -> str:
    try:
        import datetime as dt

        timestamp = float(value)
        return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _section_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, raw_sections in value.items():
        result[str(key)] = _string_list(raw_sections)
    return result


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw_value in value.items():
        try:
            result[str(key)] = int(raw_value)
        except (TypeError, ValueError):
            continue
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
