from __future__ import annotations

from typing import Any

import httpx

from .service import ReminderRecord, complete_reminder_run, get_due_reminders


class ReminderWorker:
    """Polls structured reminder rows and dispatches due messages."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def tick(self) -> int:
        reminders_cfg = self.config.get("reminders", {})
        if not bool(reminders_cfg.get("enabled", True)):
            return 0
        batch_size = int(reminders_cfg.get("due_batch_size", 20) or 20)
        due_reminders = get_due_reminders(self.config, limit=batch_size)
        for reminder in due_reminders:
            try:
                result = send_reminder_message(self.config, reminder)
                complete_reminder_run(self.config, reminder, success=True, result=result)
            except Exception as exc:
                complete_reminder_run(self.config, reminder, success=False, error=f"{type(exc).__name__}: {exc}")
        return len(due_reminders)


def send_reminder_message(config: dict[str, Any], reminder: ReminderRecord) -> dict[str, Any]:
    napcat_cfg = config.get("napcat", {})
    if not bool(napcat_cfg.get("enabled", False)):
        raise RuntimeError("NapCat is disabled")
    base_url = str(napcat_cfg.get("http_url", "") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("NapCat http_url is missing")

    target = reminder.target
    message_type = str(target.get("message_type", "private") or "private").lower()
    if message_type == "group":
        endpoint = "/send_group_msg"
        payload = {"group_id": target.get("group_id"), "message": reminder.message}
    else:
        endpoint = "/send_private_msg"
        payload = {"user_id": target.get("user_id"), "message": reminder.message}

    headers: dict[str, str] = {}
    token = str(napcat_cfg.get("token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(base_url=base_url, timeout=30.0, headers=headers) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json() if response.content else {"ok": True}
