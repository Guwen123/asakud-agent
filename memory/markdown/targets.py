from __future__ import annotations

from agent_loop.config_loader import load_config, project_path

from memory.schemas import MarkdownMemoryTarget


def get_memory_targets(config: dict | None = None) -> dict[str, MarkdownMemoryTarget]:
    config = config or load_config()
    targets: dict[str, MarkdownMemoryTarget] = {}
    for item in config["memory"]["markdown_files"]:
        targets[item["id"]] = MarkdownMemoryTarget(
            id=item["id"],
            path=project_path(item["path"]),
            title=item["title"],
            sections=list(item.get("sections", [])),
        )
    return targets


def list_markdown_memories(config: dict | None = None) -> list[dict[str, object]]:
    return [
        {
            "id": target.id,
            "path": str(target.path),
            "title": target.title,
            "sections": target.sections,
        }
        for target in get_memory_targets(config).values()
    ]


def render_memory_targets(config: dict) -> str:
    lines: list[str] = []
    for item in config.get("memory", {}).get("markdown_files", []):
        lines.append(
            f"- id={item.get('id')}, path={item.get('path')}, "
            f"title={item.get('title')}, sections={item.get('sections', [])}"
        )
    return "\n".join(lines) if lines else "无"

