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


@dataclass(frozen=True)
class WebCrawlRecord:
    id: str
    session_id: str | None
    query: str
    result: str
    ok: bool
    error: str | None
    created_at: str
    metadata: dict[str, Any] | None


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

    def add_memory_event(
        self,
        memory_type: str,
        content: str,
        session_id: str | None = None,
        reason: str | None = None,
        status: str = "pending",
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        created_at: str | None = None,
        applied_at: str | None = None,
    ) -> str:
        event_id = event_id or new_id()
        self.conn.execute(
            """
            INSERT INTO memory_events(
                id, session_id, memory_type, content, reason,
                created_at, applied_at, status, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                memory_type,
                content,
                reason,
                created_at or now_iso(),
                applied_at,
                status,
                dump_json(metadata),
            ),
        )
        self.conn.commit()
        return event_id

    def add_web_crawl(
        self,
        query: str,
        result: str,
        *,
        ok: bool = True,
        error: str | None = None,
        session_id: str | None = None,
        crawl_id: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        crawl_id = crawl_id or new_id()
        self.conn.execute(
            """
            INSERT INTO web_crawls(
                id, session_id, query, result, ok, error, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                crawl_id,
                session_id,
                query,
                result,
                1 if ok else 0,
                error,
                created_at or now_iso(),
                dump_json(metadata),
            ),
        )
        self.conn.commit()
        return crawl_id

    def get_messages(self, session_id: str, limit: int | None = None) -> list[MessageRecord]:
        if limit is None:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
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

    def count_messages(self, session_id: str, role: str | None = None) -> int:
        if role is None:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id = ? AND role = ?",
                (session_id, role),
            ).fetchone()
        return int(row["count"] if row is not None else 0)

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

    def list_web_crawls(self, limit: int = 20) -> list[WebCrawlRecord]:
        rows = self.conn.execute(
            "SELECT * FROM web_crawls ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            WebCrawlRecord(
                id=row["id"],
                session_id=row["session_id"],
                query=row["query"],
                result=row["result"],
                ok=bool(row["ok"]),
                error=row["error"],
                created_at=row["created_at"],
                metadata=_load_json(row["metadata_json"]),
            )
            for row in rows
        ]


def _load_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
