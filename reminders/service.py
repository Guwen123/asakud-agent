from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent_loop.config_loader import project_path
from db.runtime import RuntimeStore, dump_json, new_id, now_iso


VALID_RECURRENCES = {"once", "daily", "weekly"}
ACTIVE_STATUSES = {"active", "running"}


@dataclass(frozen=True)
class ReminderRecord:
    id: str
    session_id: str | None
    message: str
    recurrence: str
    timezone: str
    run_at: str | None
    time_of_day: str | None
    day_of_week: int | None
    next_run_at: str | None
    target: dict[str, Any]
    status: str
    created_at: str
    updated_at: str
    last_run_at: str | None
    metadata: dict[str, Any]


def create_reminder(
    config: dict[str, Any],
    *,
    message: str,
    target: dict[str, Any],
    session_id: str | None = None,
    recurrence: str = "once",
    run_at: str = "",
    time_of_day: str = "",
    schedule_text: str = "",
    timezone: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_message = " ".join(str(message or "").split())
    if not clean_message:
        raise ValueError("reminder message is required")

    clean_target = normalize_target(target)
    if clean_target is None:
        raise ValueError("reminder target is required; use private user_id or group_id")

    reminder_timezone = timezone or _default_timezone(config)
    schedule = resolve_schedule(
        recurrence=recurrence,
        run_at=run_at,
        time_of_day=time_of_day,
        schedule_text=schedule_text,
        timezone=reminder_timezone,
    )

    reminder_id = new_id()
    created_at = now_iso()
    store = _new_store(config)
    store.initialize()
    try:
        if session_id:
            store.create_session(session_id=session_id, title="workflow session")
        store.conn.execute(
            """
            INSERT INTO reminders(
              id, session_id, message, recurrence, timezone, run_at,
              time_of_day, day_of_week, next_run_at, target_json, status,
              created_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                reminder_id,
                session_id,
                clean_message,
                schedule["recurrence"],
                schedule["timezone"],
                schedule.get("run_at"),
                schedule.get("time_of_day"),
                schedule.get("day_of_week"),
                schedule["next_run_at"],
                dump_json(clean_target),
                created_at,
                created_at,
                dump_json(metadata or {}),
            ),
        )
        store.conn.commit()
        reminder = get_reminder(config, reminder_id)
        return {
            "ok": True,
            "reminder": reminder_to_payload(reminder),
            "summary": _confirmation_text(reminder),
        }
    finally:
        store.close()


def list_reminders(config: dict[str, Any], *, status: str = "active", limit: int = 20) -> dict[str, Any]:
    normalized_status = str(status or "active").strip().lower()
    max_rows = max(min(int(limit or 20), 100), 1)
    store = _new_store(config)
    store.initialize()
    try:
        if normalized_status == "all":
            rows = store.conn.execute(
                "SELECT * FROM reminders ORDER BY COALESCE(next_run_at, updated_at) ASC LIMIT ?",
                (max_rows,),
            ).fetchall()
        else:
            rows = store.conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = ?
                ORDER BY COALESCE(next_run_at, updated_at) ASC
                LIMIT ?
                """,
                (normalized_status, max_rows),
            ).fetchall()
        reminders = [reminder_to_payload(_row_to_reminder(row)) for row in rows]
        return {"ok": True, "count": len(reminders), "reminders": reminders}
    finally:
        store.close()


def cancel_reminder(config: dict[str, Any], *, reminder_id: str) -> dict[str, Any]:
    clean_id = str(reminder_id or "").strip()
    if not clean_id:
        raise ValueError("reminder_id is required")
    store = _new_store(config)
    store.initialize()
    try:
        row = store.conn.execute("SELECT * FROM reminders WHERE id = ?", (clean_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"reminder not found: {clean_id}"}
        updated_at = now_iso()
        store.conn.execute(
            "UPDATE reminders SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (updated_at, clean_id),
        )
        store.conn.commit()
        reminder = get_reminder(config, clean_id)
        return {"ok": True, "reminder": reminder_to_payload(reminder)}
    finally:
        store.close()


def get_due_reminders(config: dict[str, Any], *, limit: int = 20) -> list[ReminderRecord]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    max_rows = max(min(int(limit or 20), 100), 1)
    store = _new_store(config)
    store.initialize()
    try:
        rows = store.conn.execute(
            """
            SELECT * FROM reminders
            WHERE status = 'active'
              AND next_run_at IS NOT NULL
              AND next_run_at <= ?
            ORDER BY next_run_at ASC
            LIMIT ?
            """,
            (now, max_rows),
        ).fetchall()
        reminders = [_row_to_reminder(row) for row in rows]
        updated_at = now_iso()
        for reminder in reminders:
            store.conn.execute(
                "UPDATE reminders SET status = 'running', updated_at = ? WHERE id = ? AND status = 'active'",
                (updated_at, reminder.id),
            )
        store.conn.commit()
        return reminders
    finally:
        store.close()


def complete_reminder_run(
    config: dict[str, Any],
    reminder: ReminderRecord,
    *,
    success: bool,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    store = _new_store(config)
    store.initialize()
    try:
        run_created_at = now_iso()
        store.conn.execute(
            """
            INSERT INTO reminder_runs(id, reminder_id, run_at, status, result_json, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                reminder.id,
                reminder.next_run_at or run_created_at,
                "success" if success else "failed",
                dump_json(result or {}),
                error,
                run_created_at,
            ),
        )

        if success:
            next_run = next_occurrence_after(reminder)
            if next_run is None:
                status = "done"
                next_run_at = None
            else:
                status = "active"
                next_run_at = next_run
        else:
            status = "active"
            retry_delay = int(config.get("reminders", {}).get("retry_delay_seconds", 300) or 300)
            next_run_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=retry_delay)).isoformat()

        store.conn.execute(
            """
            UPDATE reminders
            SET status = ?, next_run_at = ?, last_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, next_run_at, run_created_at, run_created_at, reminder.id),
        )
        store.conn.commit()
    finally:
        store.close()


def get_reminder(config: dict[str, Any], reminder_id: str) -> ReminderRecord:
    store = _new_store(config)
    store.initialize()
    try:
        row = store.conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise ValueError(f"reminder not found: {reminder_id}")
        return _row_to_reminder(row)
    finally:
        store.close()


def resolve_schedule(
    *,
    recurrence: str,
    run_at: str,
    time_of_day: str,
    schedule_text: str,
    timezone: str,
) -> dict[str, Any]:
    clean_timezone = timezone or "Asia/Shanghai"
    tzinfo = _zoneinfo(clean_timezone)
    text = str(schedule_text or "").strip()
    clean_recurrence = _infer_recurrence(recurrence, text)
    now_local = dt.datetime.now(tzinfo)

    if clean_recurrence == "once":
        target_local = _parse_run_at(run_at, tzinfo)
        if target_local is None:
            parsed_time = _parse_time_of_day(time_of_day or text)
            if parsed_time is None:
                raise ValueError("one-time reminder requires run_at or a recognizable time")
            target_local = _infer_once_datetime(text, parsed_time, now_local)
        if target_local <= now_local:
            target_local += dt.timedelta(days=1)
        return {
            "recurrence": "once",
            "timezone": clean_timezone,
            "run_at": target_local.isoformat(),
            "time_of_day": _format_time(target_local.time()),
            "day_of_week": None,
            "next_run_at": target_local.astimezone(dt.timezone.utc).isoformat(),
        }

    parsed_time = _parse_time_of_day(time_of_day or text)
    if parsed_time is None:
        raise ValueError(f"{clean_recurrence} reminder requires time_of_day or recognizable schedule_text")

    if clean_recurrence == "weekly":
        day_of_week = _parse_day_of_week(text)
        if day_of_week is None:
            raise ValueError("weekly reminder requires a weekday, e.g. every Monday")
        next_local = _next_weekly_datetime(now_local, day_of_week, parsed_time)
    else:
        day_of_week = None
        next_local = _next_daily_datetime(now_local, parsed_time)

    return {
        "recurrence": clean_recurrence,
        "timezone": clean_timezone,
        "run_at": None,
        "time_of_day": _format_time(parsed_time),
        "day_of_week": day_of_week,
        "next_run_at": next_local.astimezone(dt.timezone.utc).isoformat(),
    }


def next_occurrence_after(reminder: ReminderRecord) -> str | None:
    if reminder.recurrence == "once":
        return None
    tzinfo = _zoneinfo(reminder.timezone)
    current = _parse_run_at(reminder.next_run_at or now_iso(), dt.timezone.utc) or dt.datetime.now(dt.timezone.utc)
    now_local = dt.datetime.now(tzinfo)
    base_local = max(current.astimezone(tzinfo), now_local)
    parsed_time = _parse_time_of_day(reminder.time_of_day or "")
    if parsed_time is None:
        return None
    if reminder.recurrence == "weekly" and reminder.day_of_week is not None:
        next_local = _next_weekly_datetime(base_local + dt.timedelta(seconds=1), reminder.day_of_week, parsed_time)
    else:
        next_local = _next_daily_datetime(base_local + dt.timedelta(seconds=1), parsed_time)
    return next_local.astimezone(dt.timezone.utc).isoformat()


def normalize_target(target: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(target, dict):
        return None
    message_type = str(target.get("message_type", "") or "").lower()
    if message_type == "group":
        group_id = _safe_int(target.get("group_id"))
        if group_id is None:
            return None
        return {"message_type": "group", "group_id": group_id}
    user_id = _safe_int(target.get("user_id"))
    if user_id is None:
        return None
    return {"message_type": "private", "user_id": user_id}


def reminder_to_payload(reminder: ReminderRecord) -> dict[str, Any]:
    return {
        "id": reminder.id,
        "session_id": reminder.session_id,
        "message": reminder.message,
        "recurrence": reminder.recurrence,
        "timezone": reminder.timezone,
        "run_at": reminder.run_at,
        "time_of_day": reminder.time_of_day,
        "day_of_week": reminder.day_of_week,
        "next_run_at": reminder.next_run_at,
        "target": reminder.target,
        "status": reminder.status,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
        "last_run_at": reminder.last_run_at,
        "metadata": reminder.metadata,
    }


def _row_to_reminder(row: Any) -> ReminderRecord:
    return ReminderRecord(
        id=str(row["id"]),
        session_id=row["session_id"],
        message=str(row["message"]),
        recurrence=str(row["recurrence"]),
        timezone=str(row["timezone"]),
        run_at=row["run_at"],
        time_of_day=row["time_of_day"],
        day_of_week=row["day_of_week"],
        next_run_at=row["next_run_at"],
        target=_loads_dict(row["target_json"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_run_at=row["last_run_at"],
        metadata=_loads_dict(row["metadata_json"]),
    )


def _new_store(config: dict[str, Any]) -> RuntimeStore:
    db_config = dict(config.get("db", {}))
    db_config.setdefault("database", config["paths"]["database"])
    db_config.setdefault("schema", config["paths"]["schema"])
    return RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))


def _default_timezone(config: dict[str, Any]) -> str:
    return str(
        config.get("reminders", {}).get("default_timezone")
        or config.get("agent", {}).get("timezone")
        or "Asia/Shanghai"
    )


def _zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def _parse_run_at(value: str, tzinfo: dt.tzinfo) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)
    return parsed.astimezone(tzinfo)


def _infer_recurrence(value: str, schedule_text: str) -> str:
    text = str(schedule_text or "").lower()
    recurrence = str(value or "once").strip().lower()
    if any(token in text for token in ("每天", "每日", "天天", "every day", "daily")):
        return "daily"
    if any(token in text for token in ("每周", "每星期", "every week", "weekly")):
        return "weekly"
    return recurrence if recurrence in VALID_RECURRENCES else "once"


def _parse_time_of_day(value: str) -> dt.time | None:
    text = str(value or "").strip().lower()
    if not text:
        return None

    match = re.search(r"(\d{1,2})(?:[:：](\d{1,2}))?\s*(am|pm)?", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        marker = match.group(3) or ""
        if marker == "pm" and hour < 12:
            hour += 12
        if marker == "am" and hour == 12:
            hour = 0
        hour = _apply_chinese_daypart(text, hour)
        return _safe_time(hour, minute)

    match = re.search(r"([零〇一二两三四五六七八九十]{1,3})\s*点(?:半|([零〇一二两三四五六七八九十]{1,3})分?)?", text)
    if match:
        hour = _chinese_number_to_int(match.group(1))
        minute = 30 if "半" in match.group(0) else _chinese_number_to_int(match.group(2) or "零")
        hour = _apply_chinese_daypart(text, hour)
        return _safe_time(hour, minute)

    return None


def _infer_once_datetime(text: str, reminder_time: dt.time, now_local: dt.datetime) -> dt.datetime:
    lowered = str(text or "").lower()
    day_offset = 0
    if "后天" in lowered:
        day_offset = 2
    elif "明天" in lowered or "tomorrow" in lowered:
        day_offset = 1
    date_match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", lowered)
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
        return dt.datetime(year, month, day, reminder_time.hour, reminder_time.minute, tzinfo=now_local.tzinfo)
    target = dt.datetime.combine(
        now_local.date() + dt.timedelta(days=day_offset),
        reminder_time,
        tzinfo=now_local.tzinfo,
    )
    if day_offset == 0 and target <= now_local:
        target += dt.timedelta(days=1)
    return target


def _next_daily_datetime(now_local: dt.datetime, reminder_time: dt.time) -> dt.datetime:
    target = dt.datetime.combine(now_local.date(), reminder_time, tzinfo=now_local.tzinfo)
    if target <= now_local:
        target += dt.timedelta(days=1)
    return target


def _next_weekly_datetime(now_local: dt.datetime, day_of_week: int, reminder_time: dt.time) -> dt.datetime:
    days_ahead = (day_of_week - now_local.weekday()) % 7
    target = dt.datetime.combine(now_local.date() + dt.timedelta(days=days_ahead), reminder_time, tzinfo=now_local.tzinfo)
    if target <= now_local:
        target += dt.timedelta(days=7)
    return target


def _parse_day_of_week(text: str) -> int | None:
    lowered = str(text or "").lower()
    mapping = {
        "周一": 0,
        "星期一": 0,
        "monday": 0,
        "mon": 0,
        "周二": 1,
        "星期二": 1,
        "tuesday": 1,
        "tue": 1,
        "周三": 2,
        "星期三": 2,
        "wednesday": 2,
        "wed": 2,
        "周四": 3,
        "星期四": 3,
        "thursday": 3,
        "thu": 3,
        "周五": 4,
        "星期五": 4,
        "friday": 4,
        "fri": 4,
        "周六": 5,
        "星期六": 5,
        "saturday": 5,
        "sat": 5,
        "周日": 6,
        "周天": 6,
        "星期日": 6,
        "星期天": 6,
        "sunday": 6,
        "sun": 6,
    }
    for token, value in mapping.items():
        if token in lowered:
            return value
    return None


def _apply_chinese_daypart(text: str, hour: int) -> int:
    if any(token in text for token in ("下午", "晚上", "今晚", "夜里", "傍晚")) and hour < 12:
        return hour + 12
    if "中午" in text and hour < 11:
        return hour + 12
    if any(token in text for token in ("凌晨", "早上", "上午")) and hour == 12:
        return 0
    return hour


def _chinese_number_to_int(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    return digits.get(text, 0)


def _safe_time(hour: int, minute: int) -> dt.time | None:
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return dt.time(hour=hour, minute=minute)


def _format_time(value: dt.time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _loads_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _confirmation_text(reminder: ReminderRecord) -> str:
    if reminder.recurrence == "once":
        return f"Created one-time reminder for {reminder.next_run_at}: {reminder.message}"
    if reminder.recurrence == "weekly":
        return f"Created weekly reminder for weekday {reminder.day_of_week} at {reminder.time_of_day}: {reminder.message}"
    return f"Created daily reminder at {reminder.time_of_day}: {reminder.message}"
