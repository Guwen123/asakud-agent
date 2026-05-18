from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def dump_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class MessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class SessionRecord:
    id: str
    title: str | None
    started_at: str


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
            "INSERT OR IGNORE INTO sessions(id, title, started_at, metadata_json) VALUES (?, ?, ?, ?)",
            (session_id, title, started_at or now_iso(), dump_json(metadata)),
        )
        self.conn.commit()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> str:
        message_id = message_id or new_id()
        self.conn.execute(
            "INSERT INTO messages(id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, created_at or now_iso()),
        )
        self.conn.commit()
        return message_id

    def get_messages(self, session_id: str, limit: int | None = None) -> list[MessageRecord]:
        sql = "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC"
        args: tuple[Any, ...] = (session_id,)
        if limit is not None:
            sql += " LIMIT ?"
            args = (session_id, limit)
        rows = self.conn.execute(sql, args).fetchall()
        return [
            MessageRecord(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_sessions(self, limit: int = 20) -> list[SessionRecord]:
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            SessionRecord(
                id=row["id"],
                title=row["title"],
                started_at=row["started_at"],
            )
            for row in rows
        ]

