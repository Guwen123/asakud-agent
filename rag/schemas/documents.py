from __future__ import annotations

from dataclasses import dataclass

from rag.chunking import chunk_text


@dataclass(frozen=True)
class RagDocument:
    id: str
    text: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class RagChunk:
    id: str
    document_id: str
    text: str
    metadata: dict[str, str]


def build_chunks(
    documents: list[RagDocument],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for document in documents:
        for index, text in enumerate(chunk_text(document.text, chunk_size, overlap)):
            chunks.append(
                RagChunk(
                    id=f"{document.id}:{index}",
                    document_id=document.id,
                    text=text,
                    metadata=document.metadata,
                )
            )
    return chunks

