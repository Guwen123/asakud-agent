from __future__ import annotations

from langchain_core.documents import Document

from rag.schemas.documents import RagChunk


def chunk_to_document(chunk: RagChunk) -> Document:
    metadata = dict(chunk.metadata)
    metadata.update({"chunk_id": chunk.id, "document_id": chunk.document_id})
    return Document(page_content=chunk.text, metadata=metadata)


def document_to_chunk(document: Document) -> RagChunk:
    return RagChunk(
        id=str(document.metadata.get("chunk_id", "")),
        document_id=str(document.metadata.get("document_id", "")),
        text=document.page_content,
        metadata={
            key: str(value)
            for key, value in document.metadata.items()
            if key not in {"chunk_id", "document_id"}
        },
    )


def chunks_to_documents(chunks: list[RagChunk]) -> list[Document]:
    return [chunk_to_document(chunk) for chunk in chunks]


def document_key(document: Document) -> str:
    return str(document.metadata.get("chunk_id") or document.page_content)

