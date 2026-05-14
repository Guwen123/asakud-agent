from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document

from rag.retrieval.bm25 import BM25Index
from rag.retrieval.dense import DenseIndex
from rag.schemas.documents import RagChunk, RagDocument, build_chunks
from rag.schemas.protocols import DenseEncoder
from rag.utils.documents import chunks_to_documents


@dataclass(frozen=True)
class RagSearchIndex:
    chunks: list[RagChunk]
    documents: list[Document]
    bm25: BM25Index
    dense: DenseIndex | None = None

    @classmethod
    def from_chunks(
        cls,
        chunks: list[RagChunk],
        dense_encoder: DenseEncoder | None = None,
    ) -> RagSearchIndex:
        documents = chunks_to_documents(chunks)
        bm25 = BM25Index.from_documents(documents)
        dense = DenseIndex.from_documents(documents, dense_encoder) if dense_encoder else None
        return cls(chunks=chunks, documents=documents, bm25=bm25, dense=dense)

    @classmethod
    def from_documents(
        cls,
        documents: list[RagDocument],
        dense_encoder: DenseEncoder | None = None,
        chunk_size: int = 800,
        overlap: int = 120,
    ) -> RagSearchIndex:
        chunks = build_chunks(documents, chunk_size=chunk_size, overlap=overlap)
        return cls.from_chunks(chunks, dense_encoder=dense_encoder)

