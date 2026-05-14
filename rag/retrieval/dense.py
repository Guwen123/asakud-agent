from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document

from rag.schemas.protocols import DenseEncoder
from rag.utils.math import cosine_similarity


@dataclass(frozen=True)
class DenseIndex:
    documents: list[Document]
    document_vectors: list[list[float]]
    encoder: DenseEncoder

    @classmethod
    def from_documents(cls, documents: list[Document], encoder: DenseEncoder) -> DenseIndex:
        vectors = encoder.embed_documents([document.page_content for document in documents])
        return cls(documents=documents, document_vectors=vectors, encoder=encoder)

    def search(self, query: str, limit: int = 20) -> list[tuple[Document, float]]:
        if not self.documents:
            return []

        query_vector = self.encoder.embed_query(query)
        scored = [
            (document, cosine_similarity(query_vector, vector))
            for document, vector in zip(self.documents, self.document_vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

