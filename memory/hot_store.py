from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HotMemoryUpdate:
    memory_id: str
    content: str
    metadata: dict[str, Any]
    created_at: float


class MemoryHotStore:
    def __init__(self, config: dict[str, Any]) -> None:
        redis_cfg = config.get("redis", {})
        hot_cfg = config.get("memory", {}).get("hot_store", {})
        self.enabled = bool(redis_cfg.get("enabled", False))
        self.namespace = str(redis_cfg.get("namespace", "asakud-agent") or "asakud-agent")
        min_flush_age = int(hot_cfg.get("flush_min_age_seconds", 86400))
        configured_ttl = int(redis_cfg.get("ttl_seconds", 604800))
        self.ttl_seconds = max(configured_ttl, min_flush_age + 86400)
        self.access_ttl_seconds = int(redis_cfg.get("access_ttl_seconds", 2592000))
        self.lock_ttl_ms = int(redis_cfg.get("lock_ttl_ms", 30000))
        self._client = None

        if not self.enabled:
            return
        try:
            from redis import Redis

            self._client = Redis.from_url(
                str(redis_cfg.get("url", "redis://localhost:6379/0")),
                decode_responses=True,
            )
            self._client.ping()
        except Exception:
            self.enabled = False
            self._client = None

    def append_update(self, memory_id: str, content: str, metadata: dict[str, Any] | None = None) -> int:
        if not self.enabled or self._client is None:
            return 0
        payload = {
            "memory_id": memory_id,
            "content": content,
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        pending_length = int(self._client.rpush(self._pending_key(memory_id), json.dumps(payload, ensure_ascii=False)))
        self._client.expire(self._pending_key(memory_id), self.ttl_seconds)
        return pending_length

    def oldest_pending_age_seconds(self, memory_id: str) -> float:
        if not self.enabled or self._client is None:
            return 0.0
        rows = self._client.lrange(self._pending_key(memory_id), 0, 0)
        if not rows:
            return 0.0
        update = self._parse_update(rows[0])
        if update is None:
            return 0.0
        return max(time.time() - update.created_at, 0.0)

    def should_flush(self, memory_id: str, min_session_turns: int, min_age_seconds: int, session_turn_count: int) -> bool:
        if not self.enabled or self._client is None:
            return False
        return (
            session_turn_count > min_session_turns
            and self.oldest_pending_age_seconds(memory_id) > min_age_seconds
        )

    def read_pending(self, memory_ids: list[str], limit: int = 20) -> dict[str, list[HotMemoryUpdate]]:
        if not self.enabled or self._client is None:
            return {}
        result: dict[str, list[HotMemoryUpdate]] = {}
        for memory_id in memory_ids:
            rows = self._client.lrange(self._pending_key(memory_id), 0, max(limit - 1, 0))
            updates = [self._parse_update(row) for row in rows]
            result[memory_id] = [item for item in updates if item is not None]
        return result

    def peek_updates(self, memory_id: str) -> list[HotMemoryUpdate]:
        if not self.enabled or self._client is None:
            return []
        rows = self._client.lrange(self._pending_key(memory_id), 0, -1)
        updates = [self._parse_update(row) for row in rows]
        return [item for item in updates if item is not None]

    def clear_updates(self, memory_id: str) -> None:
        if not self.enabled or self._client is None:
            return
        self._client.delete(self._pending_key(memory_id))

    def replace_updates(self, memory_id: str, updates: list[HotMemoryUpdate]) -> None:
        if not self.enabled or self._client is None:
            return
        key = self._pending_key(memory_id)
        self._client.delete(key)
        if not updates:
            return
        payloads = [json.dumps(self._dump_update(item), ensure_ascii=False) for item in updates]
        self._client.rpush(key, *payloads)
        self._client.expire(key, self.ttl_seconds)

    def record_entry_access(self, memory_id: str, entry_ids: list[str]) -> None:
        if not self.enabled or self._client is None:
            return
        clean_ids = [str(entry_id).strip() for entry_id in entry_ids if str(entry_id or "").strip()]
        if not clean_ids:
            return
        key = self._entry_access_key(memory_id)
        now = str(time.time())
        self._client.hset(key, mapping={entry_id: now for entry_id in clean_ids})
        self._client.expire(key, self.access_ttl_seconds)

    def read_entry_access(self, memory_id: str) -> dict[str, float]:
        if not self.enabled or self._client is None:
            return {}
        rows = self._client.hgetall(self._entry_access_key(memory_id))
        if not isinstance(rows, dict):
            return {}
        return {
            str(entry_id): _safe_float(timestamp, 0.0)
            for entry_id, timestamp in rows.items()
            if str(entry_id).strip()
        }

    def acquire_write_lock(self, memory_id: str) -> str | None:
        if not self.enabled or self._client is None:
            return None
        token = str(uuid.uuid4())
        ok = self._client.set(self._lock_key(memory_id), token, nx=True, px=self.lock_ttl_ms)
        return token if ok else None

    def release_write_lock(self, memory_id: str, token: str | None) -> None:
        if not token or not self.enabled or self._client is None:
            return
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        end
        return 0
        """
        self._client.eval(script, 1, self._lock_key(memory_id), token)

    def _pending_key(self, memory_id: str) -> str:
        return f"{self.namespace}:memory:{memory_id}:pending"

    def _lock_key(self, memory_id: str) -> str:
        return f"{self.namespace}:lock:memory:{memory_id}:write"

    def _entry_access_key(self, memory_id: str) -> str:
        return f"{self.namespace}:memory:{memory_id}:entry_last_used"

    @staticmethod
    def _parse_update(raw: str) -> HotMemoryUpdate | None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        memory_id = str(payload.get("memory_id", "") or "")
        content = str(payload.get("content", "") or "").strip()
        metadata = payload.get("metadata", {})
        created_at = _safe_float(payload.get("created_at"), time.time())
        if not memory_id or not content:
            return None
        return HotMemoryUpdate(
            memory_id=memory_id,
            content=content,
            metadata=metadata if isinstance(metadata, dict) else {},
            created_at=created_at,
        )

    @staticmethod
    def _dump_update(update: HotMemoryUpdate) -> dict[str, Any]:
        return {
            "memory_id": update.memory_id,
            "content": update.content,
            "metadata": update.metadata,
            "created_at": update.created_at,
        }


def get_hot_store(config: dict[str, Any]) -> MemoryHotStore:
    return MemoryHotStore(config)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
