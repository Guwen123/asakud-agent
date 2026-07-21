from __future__ import annotations

import unittest

from evaluators import score_output


class EvaluatorTests(unittest.TestCase):
    def test_text_and_debug_assertions_pass(self) -> None:
        output = {
            "message": "提醒已经创建，时间是每天晚上 20:00。",
            "image_ref": "",
            "debug": {
                "tool_step_count": 1,
                "tool_calls": [{"name": "create_reminder", "id": "call-1"}],
                "db_snapshot": {"recent_summary_loaded": True},
            },
        }
        assertions = {
            "must_contain": ["提醒"],
            "must_contain_any": [["20:00", "八点"]],
            "must_not_contain": ["SCHEDULED_TASKS"],
            "tool_calls_must_contain": ["create_reminder"],
            "tool_calls_must_not_contain": ["fetch_web"],
            "max_tool_steps": 2,
            "recent_summary_loaded": True,
            "image_ref": "",
        }

        self.assertEqual(score_output(output, assertions), [])

    def test_assertion_failures_are_reported(self) -> None:
        output = {
            "message": "我会记到 Markdown scheduler。",
            "debug": {
                "tool_step_count": 5,
                "tool_calls": [{"name": "fetch_web", "id": "call-1"}],
                "db_snapshot": {"recent_summary_loaded": False},
            },
        }
        assertions = {
            "must_contain": ["提醒"],
            "must_not_contain": ["Markdown scheduler"],
            "tool_calls_must_contain": ["create_reminder"],
            "tool_calls_must_not_contain": ["fetch_web"],
            "max_tool_steps": 2,
            "recent_summary_loaded": True,
        }

        failures = score_output(output, assertions)

        self.assertGreaterEqual(len(failures), 5)
        self.assertTrue(any("missing token" in item for item in failures))
        self.assertTrue(any("forbidden tool call" in item for item in failures))

    def test_regex_assertions(self) -> None:
        output = {"message": "SkillRunnerAgent 会读取 SKILL.md 后再执行脚本。"}
        assertions = {
            "must_match_regex": [r"SkillRunnerAgent.*SKILL\.md"],
            "must_not_match_regex": [r"system prompt"],
        }

        self.assertEqual(score_output(output, assertions), [])

    def test_sentence_count_assertion(self) -> None:
        output = {"message": "LangGraph is a graph runtime.\nIt manages stateful workflows.\nIt is useful for agents."}
        assertions = {"min_sentence_count": 3, "max_sentence_count": 3}

        self.assertEqual(score_output(output, assertions), [])


if __name__ == "__main__":
    unittest.main()
