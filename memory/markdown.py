from __future__ import annotations

import datetime as dt
from typing import Any

from agent_loop.config_loader import project_path


def list_markdown_memories(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "path": str(project_path(item["path"])),
            "title": item.get("title", ""),
            "sections": item.get("sections", []),
        }
        for item in config.get("memory", {}).get("markdown_files", [])
    ]


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
    entry = _render_entry(content=content, reason=reason, source=source)
    updated = _append_to_section(text, target_section, entry)
    path.write_text(updated, encoding="utf-8")

    return {"memory_id": memory_id, "path": str(path), "section": target_section, "content": content}


def _render_entry(content: str, reason: str | None, source: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    extra = f"source={source}"
    if reason:
        extra += f"; reason={reason}"
    return f"- [{timestamp}] {content.strip()} ({extra})"


def _append_to_section(markdown: str, section: str, entry: str) -> str:
    lines = markdown.splitlines()
    heading = f"## {section}"

    for i, line in enumerate(lines):
        if line.strip() != heading:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].startswith("## "):
            j += 1
        lines.insert(j, entry)
        return "\n".join(lines).rstrip() + "\n"

    if lines and lines[-1].strip():
        lines.append("")
    lines.extend([heading, "", entry, ""])
    return "\n".join(lines).rstrip() + "\n"

