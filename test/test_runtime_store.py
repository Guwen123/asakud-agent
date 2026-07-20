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


if __name__ == "__main__":
    unittest.main()
