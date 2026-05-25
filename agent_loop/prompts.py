from __future__ import annotations

import json
from typing import Any


WORKFLOW_ROUTER_PROMPT = """You are the workflow router for the agent.

Given the user's current input, decide whether this turn needs:
1. markdown memory
2. rag memory
3. tools

Return JSON only in this shape:
{
  "read_md": true,
  "read_rag": false,
  "use_tool": false,
  "read_md_after_tool": false,
  "rag_mode": "direct",
  "plan": "one short sentence"
}

Rules:
- Use read_md=true when the user is asking about long-term preferences, project rules, or stable context.
- Use read_rag=true when the user is asking for document retrieval, prior history, or long text snippets.
- Use use_tool=true when the user wants an action, an external operation, a time lookup, or anything that requires a tool.
- rag_mode must be either "direct" or "hybrid_rerank".
"""


SKILL_ROUTER_PROMPT = """You are the skill router.

Pick the most relevant 0 to 2 skills from the provided allowed_skill_ids list.
Return JSON only:
{"skill_ids": ["..."], "reason": "one short sentence"}

Rules:
- Only choose from allowed_skill_ids.
- Return an empty list when no skill is clearly relevant.
- Do not choose unrelated skills just to fill the list.
"""


MEME_VISION_PROMPT = """You analyze one meme-like image plus optional user text.

Return JSON only:
{"emotion": "a short natural Chinese emotion phrase"}

Rules:
- Focus on the most likely emotion or reaction conveyed by the image.
- Keep the emotion short and reusable.
- If the image is ambiguous, return the safest general emotion label you can infer.
"""


MEME_PICKER_PROMPT = """You are the local meme selector.

You will receive:
1. the assistant's final text reply
2. the local meme config, where each candidate only has name, emotion, and image_ref

Return JSON only:
{"image_ref": "one candidate image_ref or empty string"}

Rules:
- Only return an image_ref that already exists in the provided meme_config.
- Pick the single best meme for the reply text.
- If nothing fits well enough, return {"image_ref": ""}.
- Do not return any extra fields or explanation.
"""


LONG_TERM_MEMORY_PROMPT = """You extract long-term memory.

Based on the current user input and assistant reply, decide whether anything is worth saving.
Return JSON only:
{
  "save_to_rag": false,
  "memory_habit": "",
  "self_update": ""
}

Rules:
- Only keep stable, long-term, reusable information.
- Do not save one-off instructions, temporary state, or raw CQ image codes as long-term memory.
- memory_habit is for durable user or project preferences.
- self_update is for durable improvements in how the agent should work.
- If nothing should be saved, keep the fields empty and save_to_rag=false.
"""


SHORT_TERM_SUMMARY_PROMPT = """Summarize the following earlier messages in concise Chinese prose.

Keep:
1. stable user preferences
2. unfinished work
3. context that still matters later

Do not repeat every detail and do not use bullet points.
"""


def build_system_prompt(
    config: dict[str, Any],
    markdown_memory: dict[str, str],
    rag_items: list[str],
    skill_texts: dict[str, str],
    meme_context: dict[str, Any] | None,
    tool_names: list[str],
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
    ]

    if markdown_memory:
        sections.extend(["", "Markdown memory:"])
        for key, value in markdown_memory.items():
            sections.extend([f"[{key}]", value])

    if rag_items:
        sections.extend(["", "RAG memory:", "\n".join(rag_items)])

    if skill_texts:
        sections.extend(["", "Loaded skills:"])
        for key, value in skill_texts.items():
            sections.extend([f"[{key}]", value])

    if meme_context:
        sections.extend(
            [
                "",
                "Current meme context:",
                json.dumps(meme_context, ensure_ascii=False),
            ]
        )

    sections.extend(
        [
            "",
            "Available tools:",
            ", ".join(tool_names) if tool_names else "none",
        ]
    )
    return "\n".join(sections)
