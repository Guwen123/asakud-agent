from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from agent_loop.config_loader import project_path
from db.runtime import RuntimeStore
from memory.markdown import entry_id_for


ENTRY_RE = re.compile(r"^- \[(?P<created>[^\]]+)\]\s*(?P<body>.*?)(?:\s+\((?P<meta>[^)]*)\))?\s*$")


@dataclass(frozen=True)
class MemoryEntry:
    line_index: int
    section: str
    created: str
    body: str
    meta: dict[str, str]
    timestamp: dt.datetime


def apply_memory_forgetting(config: dict[str, Any]) -> dict[str, Any]:
    forget_cfg = _forgetting_config(config)
    if not forget_cfg.get("enabled", False):
        return {"enabled": False, "evicted": 0, "archived": 0}

    managed_ids = _managed_ids(config, forget_cfg)
    protected_ids = set(_string_list(forget_cfg.get("protected_ids", [])))
    archive_id = str(forget_cfg.get("archive_id", "core") or "core")
    archive_source_ids = set(_string_list(forget_cfg.get("archive_source_ids", ["memory", "self"])))
    files_by_id = _memory_files_by_id(config)

    archive_rows: list[MemoryEntry] = []
    summary = {
        "enabled": True,
        "merged": 0,
        "evicted": 0,
        "archived": 0,
        "pruned": 0,
        "skipped_under_budget": 0,
    }

    for memory_id in managed_ids:
        if memory_id in protected_ids or memory_id == archive_id:
            continue
        item = files_by_id.get(memory_id)
        if item is None:
            continue
        result = _compact_markdown_file(
            config=config,
            item=item,
            memory_id=memory_id,
            archive_evictions=memory_id in archive_source_ids,
        )
        summary["merged"] += result["merged"]
        summary["evicted"] += result["evicted"]
        summary["skipped_under_budget"] += result["skipped_under_budget"]
        if memory_id in archive_source_ids:
            archive_rows.extend(result["evicted_entries"])
        else:
            summary["pruned"] += result["evicted"]

    if archive_rows:
        archive_item = files_by_id.get(archive_id)
        if archive_item is not None:
            _append_archive_entries(config, archive_item, archive_id, archive_rows)
            summary["archived"] += len(archive_rows)

    if archive_id in managed_ids and archive_id not in protected_ids:
        archive_item = files_by_id.get(archive_id)
        if archive_item is not None:
            result = _compact_markdown_file(
                config=config,
                item=archive_item,
                memory_id=archive_id,
                archive_evictions=False,
            )
            summary["merged"] += result["merged"]
            summary["pruned"] += result["evicted"]
            summary["skipped_under_budget"] += result["skipped_under_budget"]

    if summary["evicted"] or summary["archived"] or summary["pruned"]:
        _append_history_event(config, summary)

    return summary


def _compact_markdown_file(
    config: dict[str, Any],
    item: dict[str, Any],
    memory_id: str,
    archive_evictions: bool,
) -> dict[str, Any]:
    path = project_path(item["path"])
    if not path.exists():
        return {"merged": 0, "evicted": 0, "evicted_entries": [], "skipped_under_budget": 0}

    original_lines = path.read_text(encoding="utf-8").splitlines()
    merged_lines, merged_count = _merge_same_content_entries(memory_id, original_lines)
    max_tokens = _max_tokens_for(config, _forgetting_config(config), memory_id)
    max_entries = int(_forgetting_config(config).get("max_entries_per_file", 0) or 0)
    token_count = _estimate_tokens("\n".join(merged_lines))
    entries = _parse_entries(merged_lines)

    over_entry_limit = max_entries > 0 and len(entries) > max_entries
    if (max_tokens <= 0 or token_count <= max_tokens) and not over_entry_limit:
        if merged_count:
            path.write_text("\n".join(merged_lines).rstrip() + "\n", encoding="utf-8")
        return {
            "merged": merged_count,
            "evicted": 0,
            "evicted_entries": [],
            "skipped_under_budget": 1,
        }

    remove_indices: set[int] = set()
    evicted_entries: list[MemoryEntry] = []
    access_times = _entry_access_times(config, memory_id)
    candidates = sorted(entries, key=lambda entry: _retention_timestamp(memory_id, entry, access_times))

    def current_lines() -> list[str]:
        return [line for index, line in enumerate(merged_lines) if index not in remove_indices]

    for entry in candidates:
        current_token_count = _estimate_tokens("\n".join(current_lines()))
        current_entry_count = len(entries) - len(evicted_entries)
        if (max_tokens <= 0 or current_token_count <= max_tokens) and (
            max_entries <= 0 or current_entry_count <= max_entries
        ):
            break
        remove_indices.add(entry.line_index)
        evicted_entries.append(_with_source_memory(entry, memory_id))

    if remove_indices:
        updated_lines = _cleanup_blank_lines(current_lines())
        path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    elif merged_count:
        path.write_text("\n".join(merged_lines).rstrip() + "\n", encoding="utf-8")

    return {
        "merged": merged_count,
        "evicted": len(evicted_entries),
        "evicted_entries": evicted_entries if archive_evictions else [],
        "skipped_under_budget": 0,
    }


def _merge_same_content_entries(memory_id: str, lines: list[str]) -> tuple[list[str], int]:
    entries = _parse_entries(lines)
    keep_by_key: dict[tuple[str, str], MemoryEntry] = {}
    remove_indices: set[int] = set()
    updated_lines = list(lines)

    for entry in entries:
        key = (entry.section, _normalize_content(entry.body))
        if not key[1]:
            continue
        current = keep_by_key.get(key)
        if current is None:
            keep_by_key[key] = entry
            updated_lines[entry.line_index] = _render_entry_line(
                entry.created,
                entry.body,
                _with_required_meta(memory_id, entry),
            )
            continue

        if entry.timestamp >= current.timestamp:
            remove_indices.add(current.line_index)
            keep_by_key[key] = entry
            updated_lines[entry.line_index] = _render_entry_line(
                entry.created,
                entry.body,
                _merge_static_meta(memory_id, entry, current),
            )
        else:
            remove_indices.add(entry.line_index)
            updated_lines[current.line_index] = _render_entry_line(
                current.created,
                current.body,
                _merge_static_meta(memory_id, current, entry),
            )

    if not remove_indices:
        changed = sum(1 for old, new in zip(lines, updated_lines) if old != new)
        return updated_lines, changed
    return [line for index, line in enumerate(updated_lines) if index not in remove_indices], len(remove_indices)


def _append_archive_entries(
    config: dict[str, Any],
    item: dict[str, Any],
    archive_id: str,
    entries: list[MemoryEntry],
) -> None:
    path = project_path(item["path"])
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_default_markdown(item), encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines()
    section = str((item.get("sections") or ["Archived Memory"])[0])
    heading = f"## {section}"
    insert_at = _section_insert_index(lines, heading)
    if insert_at is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([heading, ""])
        insert_at = len(lines)

    rendered: list[str] = []
    for entry in entries:
        body = entry.body.strip()
        source_id = str(entry.meta.get("source_memory_id") or "")
        if not source_id:
            source_id = _infer_source_memory_id(entry.meta)
        meta = {
            "id": entry_id_for(archive_id, body),
            "source": "memory_forgetting",
            "source_memory_id": source_id,
            "modified_at": _entry_timestamp_text(entry),
            "reason": "evicted_by_token_pressure",
        }
        rendered.append(_render_entry_line(entry.created, body, meta))

    for line in reversed(rendered):
        lines.insert(insert_at, line)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _with_source_memory(entry: MemoryEntry, memory_id: str) -> MemoryEntry:
    meta = dict(entry.meta)
    meta["source_memory_id"] = memory_id
    return MemoryEntry(
        line_index=entry.line_index,
        section=entry.section,
        created=entry.created,
        body=entry.body,
        meta=meta,
        timestamp=entry.timestamp,
    )


def _append_history_event(config: dict[str, Any], summary: dict[str, Any]) -> None:
    history_id = str(_forgetting_config(config).get("history_id", "history") or "history")
    store = _new_store(config)
    store.initialize()
    try:
        store.add_memory_event(
            memory_type=history_id,
            content=(
                f"Memory compaction completed: merged={summary['merged']}, "
                f"evicted={summary['evicted']}, archived={summary['archived']}, pruned={summary['pruned']}."
            ),
            reason="memory_token_pressure_compaction",
            status="applied",
            metadata=summary,
        )
    finally:
        store.close()


def _parse_entries(lines: list[str]) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    section = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        parsed = _parse_entry_line(line)
        if parsed is None:
            continue
        created, body, meta = parsed
        entries.append(
            MemoryEntry(
                line_index=index,
                section=section,
                created=created,
                body=body,
                meta=meta,
                timestamp=_entry_timestamp(created, meta),
            )
        )
    return entries


def _parse_entry_line(line: str) -> tuple[str, str, dict[str, str]] | None:
    match = ENTRY_RE.match(line.strip())
    if not match:
        return None
    return match.group("created").strip(), match.group("body").strip(), _parse_meta(match.group("meta") or "")


def _parse_meta(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def _render_entry_line(created: str, body: str, meta: dict[str, str]) -> str:
    rendered_meta = "; ".join(f"{key}={value}" for key, value in meta.items() if value)
    if rendered_meta:
        return f"- [{created}] {body.strip()} ({rendered_meta})"
    return f"- [{created}] {body.strip()}"


def _with_required_meta(memory_id: str, entry: MemoryEntry) -> dict[str, str]:
    meta = dict(entry.meta)
    meta["id"] = meta.get("id") or entry_id_for(memory_id, entry.body)
    meta["modified_at"] = meta.get("modified_at") or entry.created
    return meta


def _merge_static_meta(memory_id: str, keep: MemoryEntry, duplicate: MemoryEntry) -> dict[str, str]:
    meta = _with_required_meta(memory_id, keep)
    if not meta.get("source") and duplicate.meta.get("source"):
        meta["source"] = duplicate.meta["source"]
    if not meta.get("reason") and duplicate.meta.get("reason"):
        meta["reason"] = duplicate.meta["reason"]
    newer_ts = max(keep.timestamp, duplicate.timestamp)
    meta["modified_at"] = newer_ts.isoformat()
    return meta


def _section_insert_index(lines: list[str], heading: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        j = index + 1
        while j < len(lines) and not lines[j].startswith("## "):
            j += 1
        return j
    return None


def _cleanup_blank_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip():
            blank_count = 0
            cleaned.append(line)
            continue
        blank_count += 1
        if blank_count <= 2:
            cleaned.append(line)
    return cleaned


def _default_markdown(item: dict[str, Any]) -> str:
    lines = [f"# {item.get('title', 'Memory')}", "", str(item.get("purpose", "") or ""), ""]
    for section in item.get("sections", []) or ["General"]:
        lines.extend([f"## {section}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _entry_timestamp(created: str, meta: dict[str, str]) -> dt.datetime:
    return _parse_dt(meta.get("modified_at", "")) or _parse_dt(created) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _entry_timestamp_text(entry: MemoryEntry) -> str:
    return entry.timestamp.isoformat()


def _retention_timestamp(memory_id: str, entry: MemoryEntry, access_times: dict[str, float]) -> dt.datetime:
    entry_id = entry.meta.get("id") or entry_id_for(memory_id, entry.body)
    last_used_at = _dt_from_unix(access_times.get(entry_id))
    if last_used_at is None:
        return entry.timestamp
    return max(entry.timestamp, last_used_at)


def _entry_access_times(config: dict[str, Any], memory_id: str) -> dict[str, float]:
    try:
        from memory.hot_store import get_hot_store

        return get_hot_store(config).read_entry_access(memory_id)
    except Exception:
        return {}


def _infer_source_memory_id(meta: dict[str, str]) -> str:
    value = meta.get("source_memory_id") or meta.get("memory_id") or ""
    return str(value)


def _normalize_content(value: str) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def _estimate_tokens(value: str) -> int:
    text = str(value or "")
    if not text.strip():
        return 0
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    other_chars = re.sub(r"[\u4e00-\u9fffA-Za-z0-9_\s]", "", text)
    return len(cjk_chars) + len(latin_words) + max(len(other_chars) // 2, 0)


def _max_tokens_for(config: dict[str, Any], forget_cfg: dict[str, Any], memory_id: str) -> int:
    by_id = forget_cfg.get("max_tokens_by_id", {})
    if isinstance(by_id, dict) and memory_id in by_id:
        return max(_safe_int(by_id.get(memory_id), 0), 0)
    return max(_safe_int(forget_cfg.get("max_tokens", config.get("memory", {}).get("max_tokens")), 0), 0)


def _memory_files_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in config.get("memory", {}).get("markdown_files", []):
        memory_id = str(item.get("id", "") or "")
        if memory_id:
            result[memory_id] = item
    return result


def _managed_ids(config: dict[str, Any], forget_cfg: dict[str, Any]) -> list[str]:
    configured = _string_list(forget_cfg.get("managed_ids", []))
    if configured:
        return configured
    protected = set(_string_list(forget_cfg.get("protected_ids", [])))
    return [
        str(item.get("id"))
        for item in config.get("memory", {}).get("markdown_files", [])
        if item.get("id") and str(item.get("id")) not in protected
    ]


def _forgetting_config(config: dict[str, Any]) -> dict[str, Any]:
    memory_cfg = config.get("memory", {})
    forget_cfg = memory_cfg.get("forgetting", {})
    return forget_cfg if isinstance(forget_cfg, dict) else {}


def _new_store(config: dict[str, Any]) -> RuntimeStore:
    db_config = dict(config.get("db", {}))
    db_config.setdefault("database", config["paths"]["database"])
    db_config.setdefault("schema", config["paths"]["schema"])
    return RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))


def _parse_dt(value: str) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _dt_from_unix(value: Any) -> dt.datetime | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
