from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent_loop.config_loader import load_config
from agent_loop.context import get_current_message_target
from reminders.service import cancel_reminder as cancel_reminder_record
from reminders.service import create_reminder as create_reminder_record
from reminders.service import list_reminders as list_reminder_records


class CreateReminderInput(BaseModel):
    message: str = Field(description="Reminder message to send when the reminder fires.")
    schedule_text: str = Field(
        default="",
        description=(
            "Original natural-language schedule text, such as '今晚八点', "
            "'每天晚上八点', or 'tomorrow 20:00'."
        ),
    )
    recurrence: str = Field(
        default="once",
        description="Recurrence type: once, daily, or weekly. Use daily for 每天/每日/every day.",
    )
    run_at: str = Field(
        default="",
        description="ISO datetime for one-time reminders, preferably with timezone, e.g. 2026-07-19T20:00:00+08:00.",
    )
    time_of_day: str = Field(
        default="",
        description="HH:MM local time for recurring reminders, e.g. 20:00.",
    )
    timezone: str = Field(default="Asia/Shanghai", description="IANA timezone, e.g. Asia/Shanghai.")
    target_json: str = Field(
        default="",
        description=(
            "Optional JSON target. Usually leave empty so the current NapCat private/group message target is used. "
            "Shape: {\"message_type\":\"private\",\"user_id\":123} or {\"message_type\":\"group\",\"group_id\":456}."
        ),
    )


class ListRemindersInput(BaseModel):
    status: str = Field(default="active", description="Reminder status to list: active, done, cancelled, or all.")
    limit: int = Field(default=20, description="Maximum reminders to return.")


class CancelReminderInput(BaseModel):
    reminder_id: str = Field(description="Reminder id returned by create_reminder or list_reminders.")


@tool(args_schema=CreateReminderInput)
def create_reminder(
    message: str,
    schedule_text: str = "",
    recurrence: str = "once",
    run_at: str = "",
    time_of_day: str = "",
    timezone: str = "Asia/Shanghai",
    target_json: str = "",
) -> dict[str, Any]:
    """Create a persistent reminder. Use this when the user asks to be reminded at a time or on a schedule."""

    try:
        config = load_config()
        target = _target_from_json(target_json) or get_current_message_target()
        if target is None:
            return {
                "ok": False,
                "error": "No message target is available. Ask the user whether this should be a private or group reminder.",
            }
        return create_reminder_record(
            config,
            message=message,
            target=target,
            session_id=str(config.get("db", {}).get("default_session_id", "default") or "default"),
            recurrence=recurrence,
            run_at=run_at,
            time_of_day=time_of_day,
            schedule_text=schedule_text,
            timezone=timezone,
            metadata={"source": "create_reminder_tool"},
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@tool(args_schema=ListRemindersInput)
def list_reminders(status: str = "active", limit: int = 20) -> dict[str, Any]:
    """List persistent reminders from the local database."""

    try:
        return list_reminder_records(load_config(), status=status, limit=limit)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@tool(args_schema=CancelReminderInput)
def cancel_reminder(reminder_id: str) -> dict[str, Any]:
    """Cancel a persistent reminder by reminder id."""

    try:
        return cancel_reminder_record(load_config(), reminder_id=reminder_id)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _target_from_json(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
