from __future__ import annotations

from langchain_core.runnables import Runnable

from rag.offline.search_index import RagSearchIndex
from rag.retrieval.hybrid import hybrid_rerank_retrieve
from rag.retrieval.simple import direct_retrieve
from rag.routing.query_router import route_query_with_llm
from rag.schemas.protocols import CrossEncoderScorer
from rag.schemas.retrieval import RouteName, RoutedRetrievalResult


def routed_retrieve(
    query: str,
    index: RagSearchIndex,
    route_llm: Runnable | None = None,
    fallback_route: RouteName | None = None,
    cross_encoder_scorer: CrossEncoderScorer | None = None,
    direct_limit: int = 5,
    final_limit: int = 5,
) -> RoutedRetrievalResult:
    if route_llm is not None:
        route = route_query_with_llm(query, route_llm)
    elif fallback_route is not None:
        route = fallback_route
    else:
        raise ValueError("route_llm is required unless fallback_route is provided.")

    if route == "direct":
        results = direct_retrieve(query, index, direct_limit)
    else:
        results = hybrid_rerank_retrieve(
            query=query,
            index=index,
            cross_encoder_scorer=cross_encoder_scorer,
            final_limit=final_limit,
        )
    return RoutedRetrievalResult(route=route, results=results)
