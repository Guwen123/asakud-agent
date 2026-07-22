from __future__ import annotations

import unittest

from run_langsmith_eval import (
    case_to_langsmith_example,
    contract_assertions_evaluator,
    latency_breakdown_evaluator,
    response_shape_evaluator,
)


class LangSmithEvalTests(unittest.TestCase):
    def test_case_to_langsmith_example_maps_inputs_outputs_and_metadata(self) -> None:
        case = {
            "id": "reminder_daily_medicine",
            "category": "reminder",
            "input": "每天晚上八点提醒我吃药。",
            "message_target": {"message_type": "private", "user_id": 10001},
            "requires": ["side_effects"],
            "side_effects": True,
            "assertions": {"tool_calls_must_contain": ["create_reminder"]},
            "notes": "daily reminder case",
        }

        example = case_to_langsmith_example(case)

        self.assertEqual(example["inputs"]["case_id"], "reminder_daily_medicine")
        self.assertEqual(example["inputs"]["message_target"]["user_id"], 10001)
        self.assertEqual(example["outputs"]["assertions"], {"tool_calls_must_contain": ["create_reminder"]})
        self.assertTrue(example["metadata"]["side_effects"])

    def test_contract_assertions_evaluator_scores_pass_and_fail(self) -> None:
        reference_outputs = {
            "assertions": {
                "must_contain": ["提醒"],
                "tool_calls_must_contain": ["create_reminder"],
            }
        }
        passing = {
            "message": "提醒已经创建。",
            "debug": {"tool_calls": [{"name": "create_reminder"}]},
        }
        failing = {
            "message": "我记住了。",
            "debug": {"tool_calls": []},
        }

        self.assertEqual(
            contract_assertions_evaluator({}, passing, reference_outputs)["score"],
            1,
        )
        failed_result = contract_assertions_evaluator({}, failing, reference_outputs)
        self.assertEqual(failed_result["score"], 0)
        self.assertIn("missing", failed_result["comment"])

    def test_response_shape_evaluator_returns_message_and_latency_scores(self) -> None:
        scores = response_shape_evaluator({"message": "hello", "elapsed_seconds": 1.25})

        by_key = {item["key"]: item["score"] for item in scores}
        self.assertEqual(by_key["has_message"], 1)
        self.assertEqual(by_key["latency_seconds"], 1.25)

    def test_latency_breakdown_evaluator_returns_trace_metrics(self) -> None:
        scores = latency_breakdown_evaluator(
            {
                "debug": {
                    "performance": {
                        "trace_id": "trace-1",
                        "total_duration_ms": 123.4,
                        "nodes": [
                            {"name": "fast", "duration_ms": 10},
                            {"name": "slow", "duration_ms": 25},
                        ],
                        "tools": [{"name": "fetch_web", "duration_ms": 50}],
                        "model_calls": [{"model_key": "main_model", "duration_ms": 40}],
                        "tokens": {"total_tokens": 12, "estimated_total_tokens": 18},
                    }
                }
            }
        )

        by_key = {item["key"]: item for item in scores}
        self.assertEqual(by_key["performance_trace_present"]["score"], 1)
        self.assertEqual(by_key["trace_total_seconds"]["score"], 0.123)
        self.assertEqual(by_key["node_total_seconds"]["score"], 0.035)
        self.assertEqual(by_key["tool_total_seconds"]["score"], 0.05)
        self.assertEqual(by_key["model_total_seconds"]["score"], 0.04)
        self.assertIn("slow", by_key["slowest_node_seconds"]["comment"])
        self.assertIn("fetch_web", by_key["slowest_tool_seconds"]["comment"])
        self.assertEqual(by_key["actual_total_tokens"]["score"], 12.0)

    def test_latency_breakdown_evaluator_uses_seconds_to_stay_within_langsmith_limits(self) -> None:
        scores = latency_breakdown_evaluator(
            {
                "debug": {
                    "performance": {
                        "trace_id": "trace-long",
                        "total_duration_ms": 229503.922,
                        "nodes": [{"name": "slow", "duration_ms": 175340.559}],
                        "tools": [],
                        "model_calls": [],
                        "tokens": {},
                    }
                }
            }
        )

        by_key = {item["key"]: item for item in scores}
        self.assertEqual(by_key["trace_total_seconds"]["score"], 229.504)
        self.assertEqual(by_key["slowest_node_seconds"]["score"], 175.341)
        self.assertLess(by_key["trace_total_seconds"]["score"], 99999.9999)

    def test_latency_breakdown_evaluator_reports_missing_trace(self) -> None:
        scores = latency_breakdown_evaluator({"message": "hello"})

        self.assertEqual(scores[0]["key"], "performance_trace_present")
        self.assertEqual(scores[0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
