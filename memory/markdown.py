from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from agent_loop.config_loader import project_path


ENTRY_RE = re.compile(r"^- \[(?P<created>[^\]]+)\]\s*(?P<body>.*?)(?:\s+\((?P<meta>[^)]*)\))?\s*$")


def entry_id_for(memory_id: str, content: str) -> str:
    normalized = f"{memory_id}:{_normalize_content(content)}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def extract_markdown_entry_ids(markdown: str, memory_id: str) -> list[str]:
    entry_ids: list[str] = []
    for line in markdown.splitlines():
        parsed = _parse_entry_line(line)
        if parsed is None:
            continue
        _, body, meta = parsed
        entry_id = meta.get("id") or entry_id_for(memory_id, body)
        if entry_id not in entry_ids:
            entry_ids.append(entry_id)
    return entry_ids


def parse_markdown_entries(markdown: str, memory_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current_section = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue
        parsed = _parse_entry_line(line)
        if parsed is None:
            continue
        created, body, meta = parsed
        entries.append(
            {
                "entry_id": meta.get("id") or entry_id_for(memory_id, body),
                "section": current_section,
                "created": created,
                "modified_at": meta.get("modified_at") or created,
                "body": body,
                "meta": meta,
            }
        )
    return entries


def render_prompt_entries(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    lines: list[str] = []
    current_section = None
    for entry in entries:
        section = str(entry.get("section", "") or "General")
        if section != current_section:
            if lines:
                lines.append("")
            lines.append(f"## {section}")
            current_section = section
        body = str(entry.get("body", "") or "").strip()
        if not body:
            continue
        timestamp = str(entry.get("modified_at") or entry.get("created") or "").strip()
        if timestamp:
            lines.append(f"- [{timestamp}] {body}")
        else:
            lines.append(f"- {body}")
    return "\n".join(lines).strip()


def add_markdown_memory(
    memory_id: str,
    content: str,
    section: str | None = None,
    reason: str | None = None,
    source: str = "agent",
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    if config is None:
        raise ValueError("config is required")

    target = None
    for item in config.get("memory", {}).get("markdown_files", []):
        if item.get("id") == memory_id:
            target = item
            break
    if target is None:
        raise ValueError(f"Unknown memory id: {memory_id}")

    path = project_path(target["path"])
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {target.get('title', memory_id)}\n\n", encoding="utf-8")

    text = path.read_text(encoding="utf-8")
    target_section = section or (target.get("sections") or ["General"])[0]
    updated, merged, entry_id = _merge_or_append_to_section(
        memory_id=memory_id,
        markdown=text,
        section=target_section,
        content=content,
        reason=reason,
        source=source,
    )
    path.write_text(updated, encoding="utf-8")

    return {
        "memory_id": memory_id,
        "path": str(path),
        "section": target_section,
        "content": content,
        "merged": str(merged).lower(),
        "entry_id": entry_id,
    }


def _render_entry(
    memory_id: str,
    content: str,
    reason: str | None,
    source: str,
    timestamp: dt.datetime | None = None,
) -> str:
    created = (timestamp or dt.datetime.now(dt.timezone.utc)).isoformat()
    extra = f"id={entry_id_for(memory_id, content)}; source={source}; modified_at={created}"
    if reason:
        extra += f"; reason={reason}"
    return f"- [{created}] {content.strip()} ({extra})"


def _merge_or_append_to_section(
    memory_id: str,
    markdown: str,
    section: str,
    content: str,
    reason: str | None,
    source: str,
) -> tuple[str, bool, str]:
    lines = markdown.splitlines()
    heading = f"## {section}"
    now = dt.datetime.now(dt.timezone.utc)
    normalized_content = _normalize_content(content)
    entry_id = entry_id_for(memory_id, content)

    for i, line in enumerate(lines):
        if line.strip() != heading:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].startswith("## "):
            j += 1

        for idx in range(i + 1, j):
            parsed = _parse_entry_line(lines[idx])
            if parsed is None:
                continue
            created, body, meta = parsed
            if _normalize_content(body) != normalized_content:
                continue
            meta["id"] = meta.get("id") or entry_id_for(memory_id, body)
            if source and not meta.get("source"):
                meta["source"] = source
            if reason:
                meta["reason"] = reason
            meta["modified_at"] = now.isoformat()
            incoming_body = content.strip()
            merged_body = body if len(body) >= len(incoming_body) else incoming_body
            lines[idx] = _render_entry_line(created, merged_body, meta)
            return "\n".join(lines).rstrip() + "\n", True, meta["id"]

        entry = _render_entry(memory_id=memory_id, content=content, reason=reason, source=source, timestamp=now)
        lines.insert(j, entry)
        return "\n".join(lines).rstrip() + "\n", False, entry_id

    if lines and lines[-1].strip():
        lines.append("")
    entry = _render_entry(memory_id=memory_id, content=content, reason=reason, source=source, timestamp=now)
    lines.extend([heading, "", entry, ""])
    return "\n".join(lines).rstrip() + "\n", False, entry_id


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


def _normalize_content(value: str) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
