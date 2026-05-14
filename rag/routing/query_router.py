from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable

from rag.schemas.retrieval import RouteName

from .prompts import QUERY_ROUTE_PROMPT


def route_query_with_llm(query: str, route_llm: Runnable[Any, Any]) -> RouteName:
    response = (QUERY_ROUTE_PROMPT | route_llm).invoke({"query": query})
    text = extract_text(response).strip().lower()
    if "hybrid_rerank" in text:
        return "hybrid_rerank"
    if "direct" in text:
        return "direct"
    raise ValueError(f"LLM returned an unknown RAG route: {text!r}")


def extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(response, str):
        return response
    return str(response)

