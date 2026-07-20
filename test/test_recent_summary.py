from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compact.summary import append_recent_summary_turn, load_recent_summary


class RecentSummaryTests(unittest.TestCase):
    def test_append_without_compaction_below_token_limit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-summary-test-") as temp_dir:
            summary_path = Path(temp_dir) / "RECENT_SUMMARY.md"
            config = {
                "recent_summary": {
                    "path": str(summary_path),
                    "max_tokens": 1000,
                    "target_tokens": 300,
                    "prompt_max_chars": 4000,
                }
            }

            result = append_recent_summary_turn(config, "请记住我喜欢简洁回答", "知道了")

            self.assertFalse(result.compacted)
            self.assertTrue(summary_path.exists())
            text = summary_path.read_text(encoding="utf-8")
            self.assertIn("User: 请记住我喜欢简洁回答", text)
            self.assertIn("Assistant: 知道了", text)

    def test_compaction_runs_only_after_max_token_threshold(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-summary-test-") as temp_dir:
            summary_path = Path(temp_dir) / "RECENT_SUMMARY.md"
            config = {
                "recent_summary": {
                    "path": str(summary_path),
                    "max_tokens": 10,
                    "target_tokens": 5,
                    "prompt_max_chars": 4000,
                }
            }

            with patch("compact.summary._compact_summary", return_value="- compacted recent context") as compact:
                result = append_recent_summary_turn(
                    config,
                    "这是一段足够长的中文输入，用来触发 token 阈值压缩",
                    "这是一段足够长的中文回复，也会继续推高 token 数量",
                )

            self.assertTrue(result.compacted)
            compact.assert_called_once()
            self.assertIn("- compacted recent context", summary_path.read_text(encoding="utf-8"))

    def test_load_recent_summary_respects_prompt_max_chars(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-summary-test-") as temp_dir:
            summary_path = Path(temp_dir) / "RECENT_SUMMARY.md"
            summary_path.write_text("# Recent Summary\n\n1234567890", encoding="utf-8")
            config = {"recent_summary": {"path": str(summary_path), "prompt_max_chars": 4}}

            self.assertEqual(load_recent_summary(config), "7890")


if __name__ == "__main__":
    unittest.main()
