from __future__ import annotations

import json
import threading
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_loop.config_loader import project_path
from agent_loop.models.factory import build_chat_model
from db.runtime import RuntimeStore
from memory.forgetting import apply_memory_forgetting
from memory.hot_store import MemoryHotStore
from memory.markdown import add_markdown_memory
from prompts.memory import LONG_TERM_MEMORY_PROMPT


_LOCAL_WRITE_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_WRITE_LOCKS_GUARD = threading.Lock()


class MemoryWorker:
    """Background sub-agent for memory extraction, Redis staging, and cold snapshots."""

    def __init__(self, config: dict[str, Any], hot_store: MemoryHotStore) -> None:
        self.config = config
        self.hot_store = hot_store

    def process(self, job: Any) -> None:
        if job.kind == "long_term_update":
            self._process_long_term_update(job.payload)
        elif job.kind == "short_term_compression":
            self._process_short_term_compression(job.payload)

    def _process_long_term_update(self, payload: dict[str, Any]) -> None:
        user_input = str(payload.get("user_input", "") or "")
        assistant_output = str(payload.get("assistant_output", "") or "")
        if not user_input or not assistant_output:
            return

        model = build_chat_model(self.config, overrides={"temperature": 0.0, "max_output_tokens": 800})
        response = model.invoke(
            [
                SystemMessage(content=LONG_TERM_MEMORY_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {"user": user_input, "assistant": assistant_output},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        decision = _parse_json(_extract_text(response))
        targets = [
            (
                "memory",
                str(decision.get("memory_fact", "") or decision.get("memory_habit", "") or "").strip(),
                "Stable Facts",
                "session_memory_fact",
            ),
            (
                "self",
                str(decision.get("self_update", "") or "").strip(),
                "Self Knowledge",
                "session_self_reflection",
            ),
            (
                "pending",
                str(decision.get("pending_fact", "") or "").strip(),
                "Pending Facts",
                "session_pending_fact",
            ),
        ]
        history_event = str(decision.get("history_event", "") or "").strip()

        for memory_id, content, section, reason in targets:
            if content:
                self._stage_or_write(memory_id, content, section, reason, "memory_worker", payload)
        if history_event:
            self._write_history_event(history_event, payload)
        self._flush_ready_hot_memories(payload)

    def _process_short_term_compression(self, payload: dict[str, Any]) -> None:
        # SQLite messages are the HISTORY backend. Keep full non-system history there;
        # import_db already limits how many messages are loaded into the active turn.
        return

    def _stage_or_write(
        self,
        memory_id: str,
        content: str,
        section: str,
        reason: str,
        source: str,
        payload: dict[str, Any],
    ) -> None:
        metadata = {
            "section": section,
            "reason": reason,
            "source": source,
            "session_id": str(payload.get("session_id", "") or ""),
            "session_turn_count": _session_turn_count(payload),
        }
        hot_cfg = self.config.get("memory", {}).get("hot_store", {})
        min_session_turns = int(hot_cfg.get("flush_min_session_turns", 5))
        min_age_seconds = int(hot_cfg.get("flush_min_age_seconds", 86400))
        if self.hot_store.enabled:
            self.hot_store.append_update(memory_id, content, metadata)
            if self.hot_store.should_flush(
                memory_id,
                min_session_turns=min_session_turns,
                min_age_seconds=min_age_seconds,
                session_turn_count=_session_turn_count(payload),
            ):
                self.flush_memory_id(memory_id, min_age_seconds=min_age_seconds)
            return

        if not bool(hot_cfg.get("write_through_without_redis", False)):
            self._write_deferred_memory_event(memory_id, content, reason, metadata)
            return

        self._write_markdown_updates(memory_id, [(content, metadata)])

    def _flush_ready_hot_memories(self, payload: dict[str, Any]) -> None:
        if not self.hot_store.enabled:
            return
        hot_cfg = self.config.get("memory", {}).get("hot_store", {})
        memory_ids = _string_list(hot_cfg.get("flush_ids", ["self", "memory", "pending"]))
        min_session_turns = int(hot_cfg.get("flush_min_session_turns", 5))
        min_age_seconds = int(hot_cfg.get("flush_min_age_seconds", 86400))
        session_turn_count = _session_turn_count(payload)
        for memory_id in memory_ids:
            if self.hot_store.should_flush(
                memory_id,
                min_session_turns=min_session_turns,
                min_age_seconds=min_age_seconds,
                session_turn_count=session_turn_count,
            ):
                self.flush_memory_id(memory_id, min_age_seconds=min_age_seconds)

    def flush_memory_id(self, memory_id: str, min_age_seconds: int = 0) -> None:
        if not self.hot_store.enabled:
            return
        token = self.hot_store.acquire_write_lock(memory_id)
        if token is None:
            return
        try:
            updates = self.hot_store.peek_updates(memory_id)
            if not updates:
                return
            matured, fresh = _partition_matured_updates(updates, min_age_seconds)
            if not matured:
                return
            rows = [(item.content, item.metadata) for item in matured]
            self._write_markdown_updates(memory_id, rows)
            if fresh:
                self.hot_store.replace_updates(memory_id, fresh)
            else:
                self.hot_store.clear_updates(memory_id)
        finally:
            self.hot_store.release_write_lock(memory_id, token)

    def _write_markdown_updates(self, memory_id: str, rows: list[tuple[str, dict[str, Any]]]) -> None:
        lock = _local_write_lock(memory_id)
        with lock:
            for content, metadata in rows:
                add_markdown_memory(
                    memory_id,
                    content,
                    section=str(metadata.get("section") or _default_section(self.config, memory_id)),
                    reason=str(metadata.get("reason") or "memory_worker_update"),
                    source=str(metadata.get("source") or "memory_worker"),
                    config=self.config,
                )
            apply_memory_forgetting(self.config)

    def _write_history_event(self, content: str, payload: dict[str, Any]) -> None:
        store = _new_store(self.config)
        store.initialize()
        try:
            session_id = str(payload.get("session_id", "") or "")
            if session_id:
                store.create_session(session_id=session_id, title="workflow session")
            store.add_memory_event(
                session_id=session_id or None,
                memory_type="history",
                content=content,
                reason="session_event_log",
                status="applied",
                metadata={"source": "memory_worker"},
            )
        finally:
            store.close()

    def _write_deferred_memory_event(
        self,
        memory_id: str,
        content: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        store = _new_store(self.config)
        store.initialize()
        try:
            session_id = str(metadata.get("session_id", "") or "")
            if session_id:
                store.create_session(session_id=session_id, title="workflow session")
            store.add_memory_event(
                session_id=session_id or None,
                memory_type=memory_id,
                content=content,
                reason=reason,
                status="pending",
                metadata={**metadata, "deferred_reason": "redis_unavailable"},
            )
        finally:
            store.close()


def _new_store(config: dict[str, Any]) -> RuntimeStore:
    db_config = dict(config.get("db", {}))
    db_config.setdefault("database", config["paths"]["database"])
    db_config.setdefault("schema", config["paths"]["schema"])
    return RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))


def _default_section(config: dict[str, Any], memory_id: str) -> str:
    for item in config.get("memory", {}).get("markdown_files", []):
        if item.get("id") == memory_id:
            sections = item.get("sections") or ["General"]
            return str(sections[0])
    return "General"


def _local_write_lock(memory_id: str) -> threading.Lock:
    with _LOCAL_WRITE_LOCKS_GUARD:
        if memory_id not in _LOCAL_WRITE_LOCKS:
            _LOCAL_WRITE_LOCKS[memory_id] = threading.Lock()
        return _LOCAL_WRITE_LOCKS[memory_id]


def _session_turn_count(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("session_turn_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _partition_matured_updates(updates: list[Any], min_age_seconds: int) -> tuple[list[Any], list[Any]]:
    if min_age_seconds <= 0:
        return updates, []
    now = time.time()
    matured: list[Any] = []
    fresh: list[Any] = []
    for item in updates:
        age = max(now - float(getattr(item, "created_at", now) or now), 0.0)
        if age > min_age_seconds:
            matured.append(item)
        else:
            fresh.append(item)
    return matured, fresh


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _parse_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
