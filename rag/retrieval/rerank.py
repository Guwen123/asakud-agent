from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from langchain_core.documents import Document

from rag.schemas.protocols import CrossEncoderScorer
from rag.utils.documents import document_key


def cross_encoder_rerank(
    query: str,
    documents: list[Document],
    scorer: CrossEncoderScorer | None,
    limit: int = 20,
) -> list[tuple[Document, float]]:
    if scorer is None or not documents:
        return [(document, 0.0) for document in documents[:limit]]

    scores = scorer(query, documents)
    scored = list(zip(documents, scores))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def rrf_fuse(
    ranked_lists: list[list[tuple[Document, float]]],
    limit: int = 5,
    k: int = 60,
) -> list[tuple[Document, float]]:
    scores: defaultdict[str, float] = defaultdict(float)
    documents_by_key: dict[str, Document] = {}

    for ranked in ranked_lists:
        for rank, (document, _score) in enumerate(ranked, start=1):
            key = document_key(document)
            documents_by_key[key] = document
            scores[key] += 1.0 / (k + rank)

    fused = [(documents_by_key[key], score) for key, score in scores.items()]
    fused.sort(key=lambda item: item[1], reverse=True)
    return fused[:limit]


def unique_documents(documents: Iterable[Document]) -> list[Document]:
    unique: dict[str, Document] = {}
    for document in documents:
        unique.setdefault(document_key(document), document)
    return list(unique.values())

