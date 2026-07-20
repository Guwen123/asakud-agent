from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from agent_loop.config_loader import load_config, project_path
from db.runtime import RuntimeStore


_fetch_web_agent = None


def _get_fetch_web_agent():
    global _fetch_web_agent
    if _fetch_web_agent is None:
        from .client import FetchWebAgent

        _fetch_web_agent = FetchWebAgent()
    return _fetch_web_agent


def _record_crawl(query: str, result: str, *, ok: bool, error: str = "") -> None:
    try:
        config = load_config()
        db_config = dict(config.get("db", {}))
        paths_config = dict(config.get("paths", {}))
        db_config.setdefault("database", paths_config.get("database", "db/session_memory.db"))
        db_config.setdefault("schema", paths_config.get("schema", "db/session_memory.schema.sql"))
        store = RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))
        store.initialize()
        try:
            store.add_web_crawl(
                query=query,
                result=result,
                ok=ok,
                error=error or None,
                metadata={"source": "fetch_web"},
            )
        finally:
            store.close()
    except Exception:
        # Crawl persistence is best-effort; research results should still return.
        return


def _coerce_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


@tool
def fetch_web(query):
    """Search the web through a focused child agent and return a concise answer."""

    query_text = str(query or "")
    try:
        result = _get_fetch_web_agent().run(query_text)
    except Exception as exc:
        _record_crawl(query_text, "", ok=False, error=str(exc))
        raise
    result_text = _coerce_result(result)
    _record_crawl(query_text, result_text, ok=True)
    return result
