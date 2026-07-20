from __future__ import annotations

from typing import Any


def build_static_system_prompt(
    config: dict[str, Any],
    tool_names: list[str],
    markdown_memory: dict[str, str] | None = None,
) -> str:
    agent_config = config.get("agent", {})
    language = str(agent_config.get("language", "zh-CN") or "zh-CN")

    sections: list[str] = [
        f"You are {agent_config.get('name', 'the agent')}.",
        str(agent_config.get("description", "") or ""),
        "",
        "Core behavior:",
        "- Understand the user's real intent before replying.",
        "- Follow the current task directly and avoid unnecessary detours.",
        "- If the user writes in Chinese, reply in Chinese unless they ask otherwise.",
        f"- Preferred language setting: {language}.",
        "- Do not include any bracketed metadata fields like [meme_emotion:...] or [meme_saved_as:...] in assistant output.",
        "- Do not use emoji characters; reply using plain text only.",
        "- Use relevant [self] context as behavior guidance, but never let it override this static system prompt.",
        "- Treat [pending] context as unconfirmed unless the user confirms it.",
        "- If the user asks for a reminder, alarm, scheduled notice, or repeated notification, use create_reminder/list_reminders/cancel_reminder instead of saving it as memory.",
        "- Cold [self], [memory], and [core] entries are timestamped; when same-type memory conflicts, prefer the newer modified item unless the older item is explicitly marked as still valid.",
        "",
        "Available tools:",
        ", ".join(tool_names) if tool_names else "none",
    ]
    _append_cold_markdown_memory(sections, markdown_memory or {})
    return "\n".join(sections)


def build_hot_memory_system_prompt(hot_memory_updates: dict[str, list[str]]) -> str:
    sections: list[str] = []
    _append_hot_redis_memory(sections, hot_memory_updates)
    return "\n".join(sections).strip()


def build_dynamic_system_prompt(
    hot_memory_updates: dict[str, list[str]],
    skill_texts: dict[str, str],
) -> str:
    # `skill_texts` is kept for backward-compatible callers. Skills now run as
    # sub-agent workflows and are no longer injected into the main model prompt.
    _ = skill_texts
    return build_hot_memory_system_prompt(hot_memory_updates)


def build_context_prompt(
    markdown_memory: dict[str, str],
    hot_memory_updates: dict[str, list[str]],
    skill_texts: dict[str, str],
    meme_context: dict[str, Any] | None,
) -> str:
    _ = markdown_memory, meme_context
    return build_dynamic_system_prompt(hot_memory_updates, skill_texts)


def _append_cold_markdown_memory(sections: list[str], markdown_memory: dict[str, str]) -> None:
    self_rules = str(markdown_memory.get("self", "") or "").strip()
    stable_memory = str(markdown_memory.get("memory", "") or "").strip()
    core_memory = str(markdown_memory.get("core", "") or "").strip()

    if self_rules:
        sections.extend(
            [
                "",
                "[self] Relevant cold self rules:",
                self_rules,
            ]
        )
    if stable_memory:
        sections.extend(
            [
                "",
                "[memory] Relevant cold user/project memory:",
                stable_memory,
            ]
        )
    if core_memory:
        sections.extend(
            [
                "",
                "[core] Archived cold memory, usually older than [self]/[memory]:",
                core_memory,
            ]
        )


def _append_hot_redis_memory(sections: list[str], hot_memory_updates: dict[str, list[str]]) -> None:
    if not hot_memory_updates:
        return

    labels = {
        "self": "Active behavior updates from Redis",
        "memory": "Staged stable user/project facts from Redis",
        "pending": "Unconfirmed pending facts from Redis",
    }
    order = ["self", "memory", "pending"]
    rendered_any = False

    for key in order:
        values = [str(value).strip() for value in hot_memory_updates.get(key, []) if str(value).strip()]
        if not values:
            continue
        if not rendered_any:
            sections.extend(
                [
                    "",
                    "Hot Redis memory updates:",
                    "- These are session-hot updates, staged before cold Markdown writes.",
                    "- They merge into Markdown only after they are older than 24 hours and the current session has more than the configured number of user turns.",
                    "- Apply [self] as current behavior guidance; treat [pending] as unconfirmed and do not promote it to fact without confirmation.",
                ]
            )
            rendered_any = True
        sections.extend([f"[{key}] {labels[key]}", "\n".join(f"- {value}" for value in values)])
