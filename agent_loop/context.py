from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any


_CURRENT_MESSAGE_TARGET: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_message_target",
    default=None,
)


def set_current_message_target(target: dict[str, Any] | None) -> Token:
    clean_target = _clean_target(target)
    return _CURRENT_MESSAGE_TARGET.set(clean_target)


def reset_current_message_target(token: Token) -> None:
    _CURRENT_MESSAGE_TARGET.reset(token)


def get_current_message_target() -> dict[str, Any] | None:
    target = _CURRENT_MESSAGE_TARGET.get()
    return dict(target) if target else None


def _clean_target(target: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(target, dict):
        return None
    message_type = str(target.get("message_type", "") or "").lower()
    if message_type not in {"private", "group"}:
        return None
    clean: dict[str, Any] = {"message_type": message_type}
    if message_type == "group":
        group_id = _safe_int(target.get("group_id"))
        if group_id is None:
            return None
        clean["group_id"] = group_id
    else:
        user_id = _safe_int(target.get("user_id"))
        if user_id is None:
            return None
        clean["user_id"] = user_id
    return clean


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
