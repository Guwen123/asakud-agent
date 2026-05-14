from __future__ import annotations

from rag.offline.search_index import RagSearchIndex
from rag.schemas.retrieval import RetrievalResult
from rag.utils.documents import document_to_chunk


def direct_retrieve(
    query: str,
    index: RagSearchIndex,
    limit: int = 5,
) -> list[RetrievalResult]:
    return [
        RetrievalResult(chunk=document_to_chunk(document), score=score, source="direct")
        for document, score in index.bm25.search(query, limit)
    ]

