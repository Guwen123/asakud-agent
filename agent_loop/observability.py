from __future__ import annotations

import datetime as dt
import re
import threading
import time
import uuid
from collections import deque
from typing import Any


_TRACE_LOCK = threading.RLock()
_RECENT_TRACES: deque[dict[str, Any]] = deque(maxlen=80)


def ensure_trace(state: dict[str, Any]) -> dict[str, Any]:
    trace = state.get("performance")
    if isinstance(trace, dict):
        return trace
    trace = {
        "trace_id": str(uuid.uuid4()),
        "session_id": str(state.get("session_id", "") or ""),
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_duration_ms": 0.0,
        "nodes": [],
        "tools": [],
        "tokens": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_input_tokens": 0,
            "estimated_output_tokens": 0,
            "estimated_total_tokens": 0,
        },
        "model_calls": [],
    }
    state["performance"] = trace
    return trace


def time_node(state: dict[str, Any], name: str, fn) -> dict[str, Any]:  # noqa: ANN001
    trace = ensure_trace(state)
    started = time.perf_counter()
    ok = True
    error = ""
    result: dict[str, Any] | None = None
    try:
        result = fn(state)
        if isinstance(result, dict) and result is not state:
            result["performance"] = trace
        return result
    except Exception as exc:
        ok = False
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = _elapsed_ms(started)
        trace.setdefault("nodes", []).append(
            {
                "name": name,
                "duration_ms": duration_ms,
                "ok": ok,
                "error": error,
            }
        )


def record_tool_call(
    state: dict[str, Any],
    *,
    name: str,
    duration_ms: float,
    ok: bool,
    error: str = "",
) -> None:
    trace = ensure_trace(state)
    trace.setdefault("tools", []).append(
        {
            "name": name,
            "duration_ms": round(float(duration_ms), 3),
            "ok": bool(ok),
            "error": str(error or ""),
        }
    )


def record_model_usage(
    state: dict[str, Any],
    *,
    model_key: str,
    messages: list[Any],
    response: Any,
    duration_ms: float,
) -> None:
    trace = ensure_trace(state)
    actual = extract_usage(response)
    estimated_input = estimate_messages_tokens(messages)
    estimated_output = estimate_text_tokens(_message_text(response))
    call = {
        "model_key": model_key,
        "duration_ms": round(float(duration_ms), 3),
        "input_tokens": actual["input_tokens"],
        "output_tokens": actual["output_tokens"],
        "total_tokens": actual["total_tokens"],
        "estimated_input_tokens": estimated_input,
        "estimated_output_tokens": estimated_output,
        "estimated_total_tokens": estimated_input + estimated_output,
    }
    trace.setdefault("model_calls", []).append(call)

    tokens = trace.setdefault("tokens", {})
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        tokens[key] = int(tokens.get(key, 0) or 0) + int(call[key] or 0)
    tokens["estimated_input_tokens"] = int(tokens.get("estimated_input_tokens", 0) or 0) + estimated_input
    tokens["estimated_output_tokens"] = int(tokens.get("estimated_output_tokens", 0) or 0) + estimated_output
    tokens["estimated_total_tokens"] = int(tokens.get("estimated_total_tokens", 0) or 0) + estimated_input + estimated_output


def finalize_trace(state: dict[str, Any]) -> dict[str, Any]:
    trace = ensure_trace(state)
    started_at = _parse_iso(trace.get("started_at"))
    if started_at is not None:
        now = dt.datetime.now(dt.timezone.utc)
        trace["total_duration_ms"] = round((now - started_at).total_seconds() * 1000, 3)
    trace["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    trace["session_id"] = str(state.get("session_id", trace.get("session_id", "")) or "")
    trace["node_count"] = len(trace.get("nodes", []) or [])
    trace["tool_count"] = len(trace.get("tools", []) or [])
    trace["model_call_count"] = len(trace.get("model_calls", []) or [])
    trace["tool_step_count"] = int(state.get("tool_step_count", 0) or 0)
    with _TRACE_LOCK:
        _RECENT_TRACES.appendleft(_public_trace(trace))
    return trace


def performance_snapshot(limit: int = 20) -> dict[str, Any]:
    with _TRACE_LOCK:
        traces = list(_RECENT_TRACES)[: max(int(limit or 20), 1)]
    summary = summarize_traces(traces)
    return {
        "ok": True,
        "summary": summary,
        "traces": traces,
    }


def summarize_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not traces:
        return {
            "trace_count": 0,
            "avg_total_duration_ms": 0.0,
            "avg_tool_latency_ms": 0.0,
            "avg_node_duration_ms": 0.0,
            "total_tokens": 0,
            "estimated_total_tokens": 0,
            "slowest_node": {},
            "slowest_tool": {},
        }
    total_duration = sum(float(trace.get("total_duration_ms", 0.0) or 0.0) for trace in traces)
    node_items = [node for trace in traces for node in trace.get("nodes", []) if isinstance(node, dict)]
    tool_items = [tool for trace in traces for tool in trace.get("tools", []) if isinstance(tool, dict)]
    total_tokens = sum(int(trace.get("tokens", {}).get("total_tokens", 0) or 0) for trace in traces)
    estimated_total_tokens = sum(int(trace.get("tokens", {}).get("estimated_total_tokens", 0) or 0) for trace in traces)
    return {
        "trace_count": len(traces),
        "avg_total_duration_ms": round(total_duration / len(traces), 3),
        "avg_tool_latency_ms": _avg_duration(tool_items),
        "avg_node_duration_ms": _avg_duration(node_items),
        "total_tokens": total_tokens,
        "estimated_total_tokens": estimated_total_tokens,
        "slowest_node": _slowest(node_items),
        "slowest_tool": _slowest(tool_items),
    }


def extract_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        return {
            "input_tokens": _safe_int(usage.get("input_tokens") or usage.get("prompt_tokens")),
            "output_tokens": _safe_int(usage.get("output_tokens") or usage.get("completion_tokens")),
            "total_tokens": _safe_int(usage.get("total_tokens")),
        }
    metadata = getattr(response, "response_metadata", None)
    token_usage = metadata.get("token_usage", {}) if isinstance(metadata, dict) else {}
    if isinstance(token_usage, dict):
        input_tokens = _safe_int(token_usage.get("prompt_tokens") or token_usage.get("input_tokens"))
        output_tokens = _safe_int(token_usage.get("completion_tokens") or token_usage.get("output_tokens"))
        total_tokens = _safe_int(token_usage.get("total_tokens")) or input_tokens + output_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def estimate_messages_tokens(messages: list[Any]) -> int:
    return sum(estimate_text_tokens(_message_text(message)) for message in messages)


def estimate_text_tokens(value: str) -> int:
    text = str(value or "")
    if not text.strip():
        return 0
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    other_chars = re.sub(r"[\u4e00-\u9fffA-Za-z0-9_\s]", "", text)
    return len(cjk_chars) + len(latin_words) + max(len(other_chars) // 2, 0)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return str(content)


def _public_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": str(trace.get("trace_id", "") or ""),
        "session_id": str(trace.get("session_id", "") or ""),
        "started_at": str(trace.get("started_at", "") or ""),
        "finished_at": str(trace.get("finished_at", "") or ""),
        "total_duration_ms": round(float(trace.get("total_duration_ms", 0.0) or 0.0), 3),
        "tool_step_count": int(trace.get("tool_step_count", 0) or 0),
        "node_count": int(trace.get("node_count", 0) or 0),
        "tool_count": int(trace.get("tool_count", 0) or 0),
        "model_call_count": int(trace.get("model_call_count", 0) or 0),
        "tokens": dict(trace.get("tokens", {}) or {}),
        "nodes": list(trace.get("nodes", []) or []),
        "tools": list(trace.get("tools", []) or []),
        "model_calls": list(trace.get("model_calls", []) or []),
    }


def _avg_duration(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return round(sum(float(item.get("duration_ms", 0.0) or 0.0) for item in items) / len(items), 3)


def _slowest(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}
    return dict(max(items, key=lambda item: float(item.get("duration_ms", 0.0) or 0.0)))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _parse_iso(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
