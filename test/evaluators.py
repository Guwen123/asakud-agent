from __future__ import annotations

import re
from typing import Any


def score_output(output: dict[str, Any], assertions: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    message = str(output.get("message", "") or "")
    debug = output.get("debug", {}) if isinstance(output.get("debug", {}), dict) else {}

    failures.extend(_score_text(message, assertions))
    failures.extend(_score_image_ref(output, assertions))
    failures.extend(_score_debug(debug, assertions))
    return failures


def _score_text(message: str, assertions: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    min_chars = assertions.get("min_chars")
    if isinstance(min_chars, int) and min_chars > 0 and len(message) < min_chars:
        failures.append(f"message too short: {len(message)} < {min_chars}")

    max_chars = assertions.get("max_chars")
    if isinstance(max_chars, int) and max_chars > 0 and len(message) > max_chars:
        failures.append(f"message too long: {len(message)} > {max_chars}")

    min_sentence_count = assertions.get("min_sentence_count")
    if isinstance(min_sentence_count, int) and min_sentence_count > 0:
        actual_sentences = _count_sentence_like_segments(message)
        if actual_sentences < min_sentence_count:
            failures.append(f"too few sentence-like segments: {actual_sentences} < {min_sentence_count}")

    max_sentence_count = assertions.get("max_sentence_count")
    if isinstance(max_sentence_count, int) and max_sentence_count > 0:
        actual_sentences = _count_sentence_like_segments(message)
        if actual_sentences > max_sentence_count:
            failures.append(f"too many sentence-like segments: {actual_sentences} > {max_sentence_count}")

    for token in _string_list(assertions.get("must_contain", [])):
        if token not in message:
            failures.append(f"missing token: {token}")

    for group in assertions.get("must_contain_any", []) or []:
        choices = _string_list(group)
        if choices and not any(choice in message for choice in choices):
            failures.append(f"missing any of: {choices}")

    for forbidden in _string_list(assertions.get("must_not_contain", [])):
        if forbidden in message:
            failures.append(f"contains forbidden token: {forbidden}")

    for pattern in _string_list(assertions.get("must_match_regex", [])):
        if not re.search(pattern, message, flags=re.IGNORECASE | re.MULTILINE):
            failures.append(f"regex did not match: {pattern}")

    for pattern in _string_list(assertions.get("must_not_match_regex", [])):
        if re.search(pattern, message, flags=re.IGNORECASE | re.MULTILINE):
            failures.append(f"forbidden regex matched: {pattern}")

    return failures


def _score_image_ref(output: dict[str, Any], assertions: dict[str, Any]) -> list[str]:
    expected = assertions.get("image_ref")
    if expected is None:
        return []
    actual = str(output.get("image_ref", "") or "")
    if str(expected) != actual:
        return [f"unexpected image_ref: {actual!r} != {expected!r}"]
    return []


def _score_debug(debug: dict[str, Any], assertions: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    tool_names = [
        str(item.get("name", "") or "")
        for item in debug.get("tool_calls", [])
        if isinstance(item, dict)
    ]

    for group in assertions.get("tool_calls_must_contain_any", []) or []:
        choices = _string_list(group)
        if choices and not any(choice in tool_names for choice in choices):
            failures.append(f"missing any tool call: {choices}; actual={tool_names}")

    for tool_name in _string_list(assertions.get("tool_calls_must_contain", [])):
        if tool_name not in tool_names:
            failures.append(f"missing tool call: {tool_name}; actual={tool_names}")

    for tool_name in _string_list(assertions.get("tool_calls_must_not_contain", [])):
        if tool_name in tool_names:
            failures.append(f"forbidden tool call: {tool_name}")

    max_tool_steps = assertions.get("max_tool_steps")
    if isinstance(max_tool_steps, int) and max_tool_steps >= 0:
        actual_steps = _safe_int(debug.get("tool_step_count"), 0)
        if actual_steps > max_tool_steps:
            failures.append(f"too many tool steps: {actual_steps} > {max_tool_steps}")

    expected_recent_summary = assertions.get("recent_summary_loaded")
    if isinstance(expected_recent_summary, bool):
        snapshot = debug.get("db_snapshot", {}) if isinstance(debug.get("db_snapshot", {}), dict) else {}
        actual = bool(snapshot.get("recent_summary_loaded", False))
        if actual != expected_recent_summary:
            failures.append(f"recent_summary_loaded mismatch: {actual} != {expected_recent_summary}")

    return failures


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "")]


def _count_sentence_like_segments(message: str) -> int:
    text = re.sub(r"https?://\S+", "", str(message or ""))
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    segments = [
        item.strip(" \t\r\n-*`>：:；;，,")
        for item in re.split(r"[。！？!?]+|\n+", text)
    ]
    return sum(1 for item in segments if item)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
