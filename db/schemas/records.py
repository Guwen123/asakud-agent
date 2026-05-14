from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionRecord:
    id: str
    title: str | None
    started_at: str
    ended_at: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class MessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class MemoryEventRecord:
    id: str
    memory_type: str
    content: str
    reason: str | None
    created_at: str
    status: str
    session_id: str | None = None
    applied_at: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScheduledTaskRecord:
    id: str
    title: str
    description: str | None
    trigger_at: str
    timezone: str
    repeat_type: str
    repeat_rule: str | None
    status: str
    created_at: str
    updated_at: str
    last_triggered_at: str | None = None
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SkillRunRecord:
    id: str
    skill_name: str
    status: str
    started_at: str
    session_id: str | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    finished_at: str | None = None

