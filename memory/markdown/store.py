from __future__ import annotations

import datetime as dt

from memory.markdown.targets import get_memory_targets
from memory.schemas import MarkdownMemoryTarget


EMPTY_MARKERS = {"- None yet.", "- 暂无。"}


def add_markdown_memory(
    memory_id: str,
    content: str,
    section: str | None = None,
    reason: str | None = None,
    source: str = "agent",
    config: dict | None = None,
) -> dict[str, str]:
    targets = get_memory_targets(config)
    if memory_id not in targets:
        available = ", ".join(sorted(targets))
        raise ValueError(f"Unknown memory id: {memory_id}. Available: {available}")

    target = targets[memory_id]
    ensure_memory_file(target)

    target_section = section or (target.sections[0] if target.sections else "Notes")
    text = target.path.read_text(encoding="utf-8")
    entry = render_memory_entry(content=content, reason=reason, source=source)
    updated = append_entry_to_section(text, target_section, entry)
    target.path.write_text(updated, encoding="utf-8")

    return {
        "memory_id": memory_id,
        "path": str(target.path),
        "section": target_section,
        "content": content,
    }


def ensure_memory_file(target: MarkdownMemoryTarget) -> None:
    target.path.parent.mkdir(parents=True, exist_ok=True)
    if target.path.exists():
        return

    lines = [f"# {target.title}", ""]
    for section in target.sections:
        lines.extend([f"## {section}", "", "- 暂无。", ""])
    target.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def render_memory_entry(content: str, reason: str | None, source: str) -> str:
    safe_content = " ".join(content.strip().split())
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"- [{timestamp}] {safe_content}"
    details = [f"source={source}"]
    if reason:
        details.append(f"reason={reason.strip()}")
    return f"{line} ({'; '.join(details)})"


def append_entry_to_section(markdown: str, section: str, entry: str) -> str:
    lines = markdown.splitlines()
    heading = f"## {section}"

    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue

        insert_at = len(lines)
        for next_index in range(index + 1, len(lines)):
            if lines[next_index].startswith("## "):
                insert_at = next_index
                break

        block = lines[index + 1 : insert_at]
        cleaned_block = [item for item in block if item.strip() not in EMPTY_MARKERS]
        lines[index + 1 : insert_at] = cleaned_block

        insert_at = index + 1 + len(cleaned_block)
        while insert_at > index + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1

        lines[insert_at:insert_at] = ["", entry, ""]
        return "\n".join(lines).rstrip() + "\n"

    if lines and lines[-1].strip():
        lines.append("")
    lines.extend([heading, "", entry, ""])
    return "\n".join(lines).rstrip() + "\n"

