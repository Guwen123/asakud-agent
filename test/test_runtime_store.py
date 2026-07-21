from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from db.runtime import RuntimeStore


ROOT = Path(__file__).resolve().parents[1]


class RuntimeStoreTests(unittest.TestCase):
    def test_web_crawl_records_are_persisted_and_listed_newest_first(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-store-test-") as temp_dir:
            store = RuntimeStore(
                Path(temp_dir) / "session_memory.db",
                ROOT / "db" / "session_memory.schema.sql",
            )
            store.initialize()
            try:
                store.add_web_crawl(
                    query="first query",
                    result="first result",
                    created_at="2026-07-20T01:00:00+00:00",
                    metadata={"source": "test"},
                )
                store.add_web_crawl(
                    query="second query",
                    result="second result",
                    ok=False,
                    error="blocked",
                    created_at="2026-07-20T02:00:00+00:00",
                )

                records = store.list_web_crawls(limit=10)
            finally:
                store.close()

        self.assertEqual([record.query for record in records], ["second query", "first query"])
        self.assertFalse(records[0].ok)
        self.assertEqual(records[0].error, "blocked")
        self.assertEqual(records[1].result, "first result")
        self.assertEqual(records[1].metadata, {"source": "test"})

    def test_web_crawl_records_can_be_counted_paged_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-store-test-") as temp_dir:
            store = RuntimeStore(
                Path(temp_dir) / "session_memory.db",
                ROOT / "db" / "session_memory.schema.sql",
            )
            store.initialize()
            try:
                first_id = store.add_web_crawl(query="first", result="one", created_at="2026-07-20T01:00:00+00:00")
                store.add_web_crawl(query="second", result="two", created_at="2026-07-20T02:00:00+00:00")
                store.add_web_crawl(query="third", result="three", created_at="2026-07-20T03:00:00+00:00")

                page = store.list_web_crawls(limit=2, offset=1)
                total_before = store.count_web_crawls()
                deleted = store.delete_web_crawl(first_id)
                total_after = store.count_web_crawls()
            finally:
                store.close()

        self.assertEqual([record.query for record in page], ["second", "first"])
        self.assertEqual(total_before, 3)
        self.assertTrue(deleted)
        self.assertEqual(total_after, 2)

    def test_performance_traces_are_persisted_and_listed_newest_first(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asakud-store-test-") as temp_dir:
            store = RuntimeStore(
                Path(temp_dir) / "session_memory.db",
                ROOT / "db" / "session_memory.schema.sql",
            )
            store.initialize()
            try:
                store.add_performance_trace(
                    {
                        "trace_id": "trace-one",
                        "session_id": "session-a",
                        "started_at": "2026-07-20T01:00:00+00:00",
                        "finished_at": "2026-07-20T01:00:01+00:00",
                        "total_duration_ms": 1000,
                        "nodes": [{"name": "agent_model", "duration_ms": 900}],
                        "tools": [],
                        "model_calls": [],
                        "tokens": {"total_tokens": 42},
                    }
                )
                store.add_performance_trace(
                    {
                        "trace_id": "trace-two",
                        "session_id": "session-b",
                        "started_at": "2026-07-20T02:00:00+00:00",
                        "finished_at": "2026-07-20T02:00:01+00:00",
                        "total_duration_ms": 2000,
                        "nodes": [],
                        "tools": [{"name": "fetch_web", "duration_ms": 1200}],
                        "model_calls": [],
                        "tokens": {"estimated_total_tokens": 80},
                    }
                )

                records = store.list_performance_traces(limit=10)
            finally:
                store.close()

        self.assertEqual([record.id for record in records], ["trace-two", "trace-one"])
        self.assertEqual(records[0].trace["tools"][0]["name"], "fetch_web")
        self.assertEqual(records[1].trace["tokens"]["total_tokens"], 42)


if __name__ == "__main__":
    unittest.main()
