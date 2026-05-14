from __future__ import annotations

from typing import Callable, Protocol

from langchain_core.documents import Document


class DenseEncoder(Protocol):
    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...


CrossEncoderScorer = Callable[[str, list[Document]], list[float]]

