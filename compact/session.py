from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MessageLike(Protocol):
    role: str
    content: str


@dataclass(frozen=True)
class CompactSessionResult:
    records: list[MessageLike]
    total_records: int
    dropped_records: int
    compaction_source: str


CONTAMINATED_ASSISTANT_MARKERS = (
    "/ATRI_chat",
    "MiMo-v2.5",
    "language model",
    "system prompt",
    "[INTERNAL CONTEXT PACKAGE]",
)


def compact_session_records(records: list[MessageLike], max_messages: int) -> CompactSessionResult:
    clean_records = [
        record
        for record in records
        if not is_contaminated_assistant_history(record.role, record.content)
    ]
    if max_messages <= 0 or len(clean_records) <= max_messages:
        selected = clean_records
    else:
        selected = clean_records[-max_messages:]
    return CompactSessionResult(
        records=selected,
        total_records=len(records),
        dropped_records=max(len(clean_records) - len(selected), 0),
        compaction_source=render_compaction_source(clean_records[: max(len(clean_records) - len(selected), 0)]),
    )


def render_compaction_source(records: list[MessageLike], max_chars: int = 6000) -> str:
    lines: list[str] = []
    remaining = max(max_chars, 0)
    for record in records:
        if remaining <= 0:
            break
        role = str(record.role or "").strip() or "unknown"
        content = _normalize_text(str(record.content or ""))
        if not content:
            continue
        line = f"{role}: {content}"
        if len(line) > remaining:
            line = line[: max(remaining - 3, 0)].rstrip() + "..."
        lines.append(line)
        remaining -= len(line)
    return "\n".join(lines).strip()


def is_contaminated_assistant_history(role: str, content: str) -> bool:
    if role != "assistant":
        return False
    return any(marker in content for marker in CONTAMINATED_ASSISTANT_MARKERS)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())
