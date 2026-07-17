from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_loop.config_loader import project_path
from agent_loop.models.factory import build_chat_model
from prompts.summary import RECENT_SUMMARY_PROMPT


DEFAULT_RECENT_SUMMARY_PATH = "memory/RECENT_SUMMARY.md"


@dataclass(frozen=True)
class RecentSummaryUpdate:
    path: str
    token_count: int
    compacted: bool
    error: str = ""


def append_recent_summary_turn(
    config: dict[str, Any],
    user_input: str,
    assistant_output: str,
) -> RecentSummaryUpdate:
    summary_cfg = _summary_config(config)
    path = project_path(summary_cfg.get("path", DEFAULT_RECENT_SUMMARY_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = path.read_text(encoding="utf-8") if path.exists() else _default_summary_text()
    updated = _append_turn(existing, user_input=user_input, assistant_output=assistant_output)
    max_tokens = _safe_int(summary_cfg.get("max_tokens"), 1800)
    token_count = estimate_tokens(updated)
    if max_tokens <= 0 or token_count <= max_tokens:
        path.write_text(updated, encoding="utf-8")
        return RecentSummaryUpdate(path=str(path), token_count=token_count, compacted=False)

    try:
        compacted_text = _compact_summary(config, updated, target_tokens=_safe_int(summary_cfg.get("target_tokens"), 900))
        path.write_text(_render_compacted_summary(compacted_text), encoding="utf-8")
        return RecentSummaryUpdate(
            path=str(path),
            token_count=estimate_tokens(compacted_text),
            compacted=True,
        )
    except Exception as exc:
        path.write_text(updated, encoding="utf-8")
        return RecentSummaryUpdate(
            path=str(path),
            token_count=token_count,
            compacted=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def load_recent_summary(config: dict[str, Any]) -> str:
    path = project_path(_summary_config(config).get("path", DEFAULT_RECENT_SUMMARY_PATH))
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not text or text == _default_summary_text().strip():
        return ""
    max_chars = _safe_int(_summary_config(config).get("prompt_max_chars"), 4000)
    if max_chars > 0 and len(text) > max_chars:
        return text[-max_chars:].strip()
    return text


def estimate_tokens(value: str) -> int:
    text = str(value or "")
    if not text.strip():
        return 0
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    other_chars = re.sub(r"[\u4e00-\u9fffA-Za-z0-9_\s]", "", text)
    return len(cjk_chars) + len(latin_words) + max(len(other_chars) // 2, 0)


def _append_turn(existing: str, user_input: str, assistant_output: str) -> str:
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    blocks = [existing.rstrip(), "", f"## Turn {timestamp}", "", f"User: {user_input.strip()}"]
    if assistant_output.strip():
        blocks.append(f"Assistant: {assistant_output.strip()}")
    return "\n".join(blocks).rstrip() + "\n"


def _compact_summary(config: dict[str, Any], source: str, target_tokens: int) -> str:
    model = build_chat_model(config, overrides={"temperature": 0.0, "max_output_tokens": max(target_tokens, 300)})
    response = model.invoke(
        [
            SystemMessage(content=RECENT_SUMMARY_PROMPT),
            HumanMessage(
                content=(
                    f"Target max tokens: {target_tokens}\n\n"
                    "Conversation summary/source to compact:\n"
                    f"{source}"
                )
            ),
        ]
    )
    content = getattr(response, "content", "")
    return str(content if isinstance(content, str) else content).strip()


def _render_compacted_summary(summary: str) -> str:
    body = summary.strip() or "- No durable recent context."
    return f"# Recent Summary\n\n{body}\n"


def _default_summary_text() -> str:
    return "# Recent Summary\n\n"


def _summary_config(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("recent_summary", {})
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
