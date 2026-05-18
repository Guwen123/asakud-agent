from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .config_loader import project_path

TASK_LINE_RE = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*)([^|]+?)\s*\|\s*(.+?)\s*$")
TIME_FORMAT_HINT = "Use ISO datetime, e.g. 2026-05-17T21:30:00+08:00"


@dataclass
class ScheduledTask:
    line_index: int
    trigger_at: dt.datetime
    content: str


class MarkdownTaskScheduler:
    def __init__(
        self,
        config: dict,
        execute_task: Callable[[str], Awaitable[None]],
    ) -> None:
        self.config = config
        self.execute_task = execute_task
        self.schedule_path = self._resolve_schedule_path(config)

    async def tick(self) -> int:
        self.schedule_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.schedule_path.exists():
            self.schedule_path.write_text(self._default_schedule_markdown(), encoding="utf-8")
            return 0

        original = self.schedule_path.read_text(encoding="utf-8")
        lines = original.splitlines()
        now = dt.datetime.now(dt.timezone.utc)
        due_tasks = self._find_due_tasks(lines, now)
        remove_indexes = self._find_done_task_indexes(lines)

        if not due_tasks and not remove_indexes:
            return 0

        for task in due_tasks:
            try:
                await self.execute_task(task.content)
            except Exception as exc:
                print(f"[scheduler] skip task due to error: {exc}; task={task.content}")
            finally:
                remove_indexes.add(task.line_index)

        for index in sorted(remove_indexes, reverse=True):
            if 0 <= index < len(lines):
                del lines[index]

        lines = self._cleanup_none_yet(lines)

        updated = "\n".join(lines).rstrip() + "\n"
        self.schedule_path.write_text(updated, encoding="utf-8")
        return len(remove_indexes)

    def _find_due_tasks(self, lines: list[str], now_utc: dt.datetime) -> list[ScheduledTask]:
        tasks: list[ScheduledTask] = []
        for idx, line in enumerate(lines):
            match = TASK_LINE_RE.match(line)
            if not match:
                continue
            status = match.group(2).strip().lower()
            if status == "x":
                continue
            trigger_text = match.group(4).strip()
            content = match.group(5).strip()
            trigger_at = self._parse_datetime(trigger_text)
            if trigger_at is None:
                continue
            if trigger_at <= now_utc:
                tasks.append(ScheduledTask(line_index=idx, trigger_at=trigger_at, content=content))
        return tasks

    @staticmethod
    def _parse_datetime(text: str) -> dt.datetime | None:
        try:
            value = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)

    @staticmethod
    def _find_done_task_indexes(lines: list[str]) -> set[int]:
        done_indexes: set[int] = set()
        for idx, line in enumerate(lines):
            match = TASK_LINE_RE.match(line)
            if not match:
                continue
            if match.group(2).strip().lower() == "x":
                done_indexes.add(idx)
        return done_indexes

    @staticmethod
    def _cleanup_none_yet(lines: list[str]) -> list[str]:
        has_task = any(TASK_LINE_RE.match(line) for line in lines)
        if not has_task:
            return lines
        return [line for line in lines if line.strip() != "- None yet."]

    @staticmethod
    def _resolve_schedule_path(config: dict) -> Path:
        memory_files = config.get("memory", {}).get("markdown_files", [])
        for item in memory_files:
            if item.get("id") == "scheduled":
                return project_path(item["path"])
        fallback_candidates = [
            project_path("memory/SCHEDULED_TASKS.md"),
        ]
        for path in fallback_candidates:
            if path.exists():
                return path
        return fallback_candidates[0]

    @staticmethod
    def _default_schedule_markdown() -> str:
        return (
            "# Scheduled Tasks\n\n"
            "Use line format below in Active section:\n"
            f"- [ ] 2026-05-17T21:30:00+08:00 | send hello to user ({TIME_FORMAT_HINT})\n\n"
            "## Active\n\n"
            "- None yet.\n"
        )
