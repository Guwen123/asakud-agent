from __future__ import annotations

from rag.offline.search_index import RagSearchIndex
from rag.schemas.protocols import CrossEncoderScorer
from rag.schemas.retrieval import RetrievalResult
from rag.utils.documents import document_to_chunk

from .rerank import cross_encoder_rerank, rrf_fuse, unique_documents


def hybrid_rerank_retrieve(
    query: str,
    index: RagSearchIndex,
    cross_encoder_scorer: CrossEncoderScorer | None = None,
    bm25_limit: int = 20,
    dense_limit: int = 20,
    rerank_limit: int = 20,
    final_limit: int = 5,
) -> list[RetrievalResult]:
    bm25_ranked = index.bm25.search(query, bm25_limit)
    dense_ranked = index.dense.search(query, dense_limit) if index.dense else []

    candidates = unique_documents([doc for doc, _score in bm25_ranked + dense_ranked])
    cross_ranked = cross_encoder_rerank(query, candidates, cross_encoder_scorer, rerank_limit)
    fused = rrf_fuse([bm25_ranked, dense_ranked, cross_ranked], final_limit)

    return [
        RetrievalResult(chunk=document_to_chunk(document), score=score, source="hybrid_rerank")
        for document, score in fused
    ]

