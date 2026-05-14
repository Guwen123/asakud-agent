from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from db.schemas import (
    MemoryEventRecord,
    MessageRecord,
    ScheduledTaskRecord,
    SessionRecord,
    SkillRunRecord,
)
from db.utils import dump_json, load_json, new_id, now_iso


class RuntimeStore:
    def __init__(self, database_path: Path, schema_path: Path) -> None:
        self.database_path = database_path
        self.schema_path = schema_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.database_path)
        self.conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        schema = self.schema_path.read_text(encoding="utf-8")
        self.conn.executescript(schema)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_session(
        self,
        session_id: str | None = None,
        title: str | None = None,
        started_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        session_id = session_id or new_id()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sessions(id, title, started_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, title, started_at or now_iso(), dump_json(metadata)),
        )
        self.conn.commit()
        return session_id

    def end_session(self, session_id: str, ended_at: str | None = None) -> None:
        self.conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (ended_at or now_iso(), session_id),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._session_from_row(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        message_id = message_id or new_id()
        self.conn.execute(
            """
            INSERT INTO messages(id, session_id, role, content, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, created_at or now_iso(), dump_json(metadata)),
        )
        self.conn.commit()
        return message_id

    def get_messages(self, session_id: str, limit: int | None = None) -> list[MessageRecord]:
        sql = "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC"
        params: tuple[Any, ...] = (session_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (session_id, limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._message_from_row(row) for row in rows]

    def clear_messages(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.commit()

    def search_messages(self, query: str, limit: int = 10) -> list[MessageRecord]:
        rows = self.conn.execute(
            """
            SELECT m.*
            FROM messages_fts f
            JOIN messages m ON m.id = f.message_id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def add_memory_event(
        self,
        memory_type: str,
        content: str,
        reason: str | None = None,
        session_id: str | None = None,
        status: str = "pending",
        event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event_id = event_id or new_id()
        self.conn.execute(
            """
            INSERT INTO memory_events(
              id, session_id, memory_type, content, reason, created_at, status, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, session_id, memory_type, content, reason, now_iso(), status, dump_json(metadata)),
        )
        self.conn.commit()
        return event_id

    def list_memory_events(self, status: str | None = None, limit: int = 50) -> list[MemoryEventRecord]:
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM memory_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memory_events WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [self._memory_event_from_row(row) for row in rows]

    def mark_memory_event_applied(self, event_id: str, applied_at: str | None = None) -> None:
        self.conn.execute(
            "UPDATE memory_events SET status = 'applied', applied_at = ? WHERE id = ?",
            (applied_at or now_iso(), event_id),
        )
        self.conn.commit()

    def add_scheduled_task(
        self,
        title: str,
        trigger_at: str,
        description: str | None = None,
        timezone: str = "Asia/Shanghai",
        repeat_type: str = "none",
        repeat_rule: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        task_id = task_id or new_id()
        timestamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO scheduled_tasks(
              id, title, description, trigger_at, timezone, repeat_type, repeat_rule,
              status, created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                task_id,
                title,
                description,
                trigger_at,
                timezone,
                repeat_type,
                repeat_rule,
                timestamp,
                timestamp,
                dump_json(metadata),
            ),
        )
        self.conn.commit()
        return task_id

    def list_due_tasks(self, now: str | None = None, limit: int = 50) -> list[ScheduledTaskRecord]:
        rows = self.conn.execute(
            """
            SELECT * FROM scheduled_tasks
            WHERE status IN ('pending', 'active') AND trigger_at <= ?
            ORDER BY trigger_at ASC
            LIMIT ?
            """,
            (now or now_iso(), limit),
        ).fetchall()
        return [self._scheduled_task_from_row(row) for row in rows]

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        last_triggered_at: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE scheduled_tasks
            SET status = ?, result_json = ?, last_triggered_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, dump_json(result), last_triggered_at, now_iso(), task_id),
        )
        self.conn.commit()

    def add_skill_run(
        self,
        skill_name: str,
        status: str,
        session_id: str | None = None,
        input: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or new_id()
        self.conn.execute(
            """
            INSERT INTO skill_runs(id, skill_name, session_id, input_json, status, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, skill_name, session_id, dump_json(input), status, now_iso()),
        )
        self.conn.commit()
        return run_id

    def finish_skill_run(self, run_id: str, status: str, output: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "UPDATE skill_runs SET status = ?, output_json = ?, finished_at = ? WHERE id = ?",
            (status, dump_json(output), now_iso(), run_id),
        )
        self.conn.commit()

    def list_skill_runs(self, session_id: str | None = None, limit: int = 50) -> list[SkillRunRecord]:
        if session_id is None:
            rows = self.conn.execute(
                "SELECT * FROM skill_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM skill_runs WHERE session_id = ? ORDER BY started_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._skill_run_from_row(row) for row in rows]

    def _session_from_row(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            title=row["title"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            metadata=load_json(row["metadata_json"]),
        )

    def _message_from_row(self, row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=load_json(row["metadata_json"]),
        )

    def _memory_event_from_row(self, row: sqlite3.Row) -> MemoryEventRecord:
        return MemoryEventRecord(
            id=row["id"],
            session_id=row["session_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            reason=row["reason"],
            created_at=row["created_at"],
            applied_at=row["applied_at"],
            status=row["status"],
            metadata=load_json(row["metadata_json"]),
        )

    def _scheduled_task_from_row(self, row: sqlite3.Row) -> ScheduledTaskRecord:
        return ScheduledTaskRecord(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            trigger_at=row["trigger_at"],
            timezone=row["timezone"],
            repeat_type=row["repeat_type"],
            repeat_rule=row["repeat_rule"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_triggered_at=row["last_triggered_at"],
            result=load_json(row["result_json"]),
            metadata=load_json(row["metadata_json"]),
        )

    def _skill_run_from_row(self, row: sqlite3.Row) -> SkillRunRecord:
        return SkillRunRecord(
            id=row["id"],
            skill_name=row["skill_name"],
            session_id=row["session_id"],
            input=load_json(row["input_json"]),
            output=load_json(row["output_json"]),
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

