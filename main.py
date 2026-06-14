from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

from agent_loop.bootstrap import bootstrap
from agent_loop.config_loader import load_config
from agent_loop.loop import run_agent_once_async
from agent_loop.scheduler import MarkdownTaskScheduler


class SendMessageRequest(BaseModel):
    message_type: str = "private"
    user_id: int | None = None
    group_id: int | None = None
    message: str
    image_ref: str | None = None


async def scheduled_task_loop(app: FastAPI) -> None:
    while True:
        interval = app.state.config.get("server", {}).get("scheduler_interval_seconds", 30)
        try:
            await app.state.scheduler.tick()
        except Exception as exc:
            print(f"[scheduler_loop] error: {exc}")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    app.state.config = load_config()
    app.state.last_message_target = None
    app.state.scheduler = MarkdownTaskScheduler(
        app.state.config,
        execute_task=lambda task_content: _execute_scheduled_task(app, task_content),
    )
    app.state.scheduler_task = asyncio.create_task(scheduled_task_loop(app), name="scheduler_loop")
    try:
        yield
    finally:
        app.state.scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.scheduler_task


app = FastAPI(
    title="Sakuro Agent",
    description="Long-running local Agent service.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/getMessage")
async def get_message(request: Request) -> dict[str, Any]:
    try:
        event = await request.json()
    except Exception:
        event = {}

    config = app.state.config
    napcat = config.get("napcat", {})
    if not napcat.get("enabled", False):
        return {"ok": False, "reason": "napcat_disabled"}

    if str(event.get("post_type", "")).lower() != "message":
        return {"ok": True, "ignored": True}
    if _is_self_message(event):
        return {"ok": True, "ignored": True, "reason": "self_message"}

    message_text = _extract_agent_message(event)
    if not message_text.strip():
        return {"ok": True, "ignored": True, "reason": "not_addressed_to_agent"}

    target = _event_to_target(event)
    app.state.last_message_target = target

    reply = await run_agent_once_async(message_text)
    send_result = await _send_message(
        app,
        target.copy(
            update={
                "message": reply.get("message", ""),
                "image_ref": reply.get("image_ref", ""),
            }
        ),
    )
    return {"ok": True, "reply": reply, "send_result": send_result}


@app.post("/sendMessage")
async def send_message(request: SendMessageRequest) -> dict[str, Any]:
    result = await _send_message(app, request)
    return {"ok": True, "result": result}


async def _execute_scheduled_task(app: FastAPI, task_content: str) -> None:
    payload = _parse_scheduled_task_payload(task_content, app.state.last_message_target)
    if payload is None:
        await run_agent_once_async(task_content)
        return
    reply = await run_agent_once_async(payload.message)
    await _send_message(
        app,
        payload.copy(
            update={
                "message": reply.get("message", ""),
                "image_ref": reply.get("image_ref", ""),
            }
        ),
    )


async def _send_message(app: FastAPI, request: SendMessageRequest) -> dict[str, Any]:
    napcat_cfg = app.state.config.get("napcat", {})
    base_url = str(napcat_cfg.get("http_url", "")).rstrip("/")
    token = str(napcat_cfg.get("token", "")).strip()
    if not base_url:
        return {"ok": False, "reason": "missing_http_url"}

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    message_type = str(request.message_type or "private").lower()
    text_message = str(request.message or "").strip()
    image_ref = str(request.image_ref or "").strip().replace("\\", "/")

    if message_type == "group":
        endpoint = "/send_group_msg"

        def build_body(message: str) -> dict[str, Any]:
            return {"group_id": request.group_id, "message": message}

    else:
        endpoint = "/send_private_msg"

        def build_body(message: str) -> dict[str, Any]:
            return {"user_id": request.user_id, "message": message}

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=headers) as client:
        results: dict[str, Any] = {}
        if text_message:
            resp = await client.post(endpoint, json=build_body(text_message))
            resp.raise_for_status()
            results["text"] = resp.json() if resp.content else {"ok": True}
        if image_ref:
            image_message = f"[CQ:image,file={image_ref}]"
            resp = await client.post(endpoint, json=build_body(image_message))
            resp.raise_for_status()
            results["image"] = resp.json() if resp.content else {"ok": True}
        return results or {"ok": False, "reason": "empty_message"}


def _extract_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        chunks: list[str] = []
        for seg in message:
            if not isinstance(seg, dict):
                continue
            data = seg.get("data", {})
            if seg.get("type") == "text" and isinstance(data, dict):
                chunks.append(str(data.get("text", "")))
            elif seg.get("type") == "image" and isinstance(data, dict):
                url = str(data.get("url", "") or data.get("file", "")).strip()
                if url:
                    chunks.append(f"[CQ:image,url={url}]")
        return "".join(chunks)
    return str(message or "")


def _extract_agent_message(event: dict[str, Any]) -> str:
    message_type = str(event.get("message_type", "private") or "private").lower()
    message = event.get("message")

    if message_type != "group":
        return _extract_text(message)

    self_id = _to_optional_int(event.get("self_id"))
    if self_id is None:
        return ""

    if isinstance(message, list):
        if not _has_at_segment(message, self_id):
            return ""
        return _strip_at_segments(_extract_text(_filter_non_at_segments(message, self_id)))

    raw_text = _extract_text(message)
    if not _contains_cq_at(raw_text, self_id):
        return ""
    return _strip_at_segments(raw_text, self_id=self_id)


def _has_at_segment(message: list[Any], self_id: int) -> bool:
    target = str(self_id)
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if str(seg.get("type", "")).lower() != "at":
            continue
        data = seg.get("data", {})
        if isinstance(data, dict) and str(data.get("qq", "")).strip() == target:
            return True
    return False


def _filter_non_at_segments(message: list[Any], self_id: int) -> list[Any]:
    target = str(self_id)
    kept: list[Any] = []
    for seg in message:
        if not isinstance(seg, dict):
            kept.append(seg)
            continue
        if str(seg.get("type", "")).lower() != "at":
            kept.append(seg)
            continue
        data = seg.get("data", {})
        qq = str(data.get("qq", "")).strip() if isinstance(data, dict) else ""
        if qq != target:
            kept.append(seg)
    return kept


def _contains_cq_at(text: str, self_id: int) -> bool:
    pattern = re.compile(rf"\[CQ:at,qq={self_id}(?:,[^\]]*)?\]")
    return bool(pattern.search(text))


def _strip_at_segments(text: str, self_id: int | None = None) -> str:
    value = str(text or "")
    if self_id is None:
        value = re.sub(r"\[CQ:at,qq=\d+(?:,[^\]]*)?\]", " ", value)
    else:
        value = re.sub(rf"\[CQ:at,qq={self_id}(?:,[^\]]*)?\]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_self_message(event: dict[str, Any]) -> bool:
    self_id = _to_optional_int(event.get("self_id"))
    user_id = _to_optional_int(event.get("user_id"))
    sender = event.get("sender", {})
    sender_id = _to_optional_int(sender.get("user_id")) if isinstance(sender, dict) else None
    return self_id is not None and (self_id == user_id or self_id == sender_id)


def _event_to_target(event: dict[str, Any]) -> SendMessageRequest:
    return SendMessageRequest(
        message_type=str(event.get("message_type", "private")),
        user_id=_to_optional_int(event.get("user_id")),
        group_id=_to_optional_int(event.get("group_id")),
        message="",
    )


def _parse_scheduled_task_payload(
    task_content: str,
    fallback_target: SendMessageRequest | None,
) -> SendMessageRequest | None:
    raw = task_content.strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = str(payload.get("message", "") or payload.get("content", "")).strip()
            if not message:
                return None
            return SendMessageRequest(
                message_type=str(payload.get("message_type", "private")),
                user_id=_to_optional_int(payload.get("user_id")),
                group_id=_to_optional_int(payload.get("group_id")),
                message=message,
            )
    if fallback_target is None:
        return None
    return fallback_target.copy(update={"message": raw})


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    server = config.get("server", {})
    uvicorn.run(
        "main:app",
        host=server.get("host", "127.0.0.1"),
        port=server.get("port", 8000),
        reload=server.get("reload", False),
    )
