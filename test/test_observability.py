from __future__ import annotations

import unittest

from agent_loop.observability import (
    ensure_trace,
    extract_usage,
    finalize_trace,
    performance_snapshot,
    record_model_usage,
    record_tool_call,
    summarize_traces,
    time_node,
)


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeResponse:
    content = "好的"
    usage_metadata = {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
    }


class ObservabilityTests(unittest.TestCase):
    def test_time_node_records_duration(self) -> None:
        state = {"session_id": "test"}

        def node(current):
            current["value"] = 1
            return current

        result = time_node(state, "import_db", node)

        self.assertEqual(result["value"], 1)
        self.assertEqual(result["performance"]["nodes"][0]["name"], "import_db")
        self.assertGreaterEqual(result["performance"]["nodes"][0]["duration_ms"], 0)

    def test_record_tool_and_model_usage(self) -> None:
        state = {"session_id": "test"}
        ensure_trace(state)

        record_tool_call(state, name="fetch_web", duration_ms=12.5, ok=True)
        record_model_usage(
            state,
            model_key="main_model",
            messages=[FakeMessage("hello")],
            response=FakeResponse(),
            duration_ms=33.3,
        )

        trace = state["performance"]
        self.assertEqual(trace["tools"][0]["name"], "fetch_web")
        self.assertEqual(trace["tokens"]["total_tokens"], 14)
        self.assertGreater(trace["tokens"]["estimated_total_tokens"], 0)

    def test_finalize_trace_is_visible_in_snapshot(self) -> None:
        state = {"session_id": "snapshot-test"}
        ensure_trace(state)
        record_tool_call(state, name="create_reminder", duration_ms=5, ok=True)
        finalize_trace(state)

        snapshot = performance_snapshot(limit=5)

        self.assertTrue(snapshot["ok"])
        self.assertGreaterEqual(snapshot["summary"]["trace_count"], 1)
        self.assertTrue(any(item["session_id"] == "snapshot-test" for item in snapshot["traces"]))

    def test_summarize_traces_finds_slowest_items(self) -> None:
        summary = summarize_traces(
            [
                {
                    "total_duration_ms": 100,
                    "tokens": {"total_tokens": 11, "estimated_total_tokens": 20},
                    "nodes": [
                        {"name": "fast", "duration_ms": 1},
                        {"name": "slow", "duration_ms": 9},
                    ],
                    "tools": [{"name": "fetch_web", "duration_ms": 30}],
                }
            ]
        )

        self.assertEqual(summary["trace_count"], 1)
        self.assertEqual(summary["slowest_node"]["name"], "slow")
        self.assertEqual(summary["slowest_tool"]["name"], "fetch_web")
        self.assertEqual(summary["total_tokens"], 11)

    def test_extract_usage_supports_usage_metadata(self) -> None:
        self.assertEqual(
            extract_usage(FakeResponse()),
            {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        )


if __name__ == "__main__":
    unittest.main()
