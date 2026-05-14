from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from langchain_core.documents import Document

from rag.utils.text import tokenize


@dataclass(frozen=True)
class BM25Index:
    documents: list[Document]
    tokenized_documents: list[list[str]]
    document_frequency: Counter[str]
    average_document_length: float
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def from_documents(
        cls,
        documents: list[Document],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> BM25Index:
        tokenized_documents = [tokenize(document.page_content) for document in documents]
        document_frequency: Counter[str] = Counter()
        for terms in tokenized_documents:
            document_frequency.update(set(terms))

        if tokenized_documents:
            average_document_length = sum(len(terms) for terms in tokenized_documents) / len(
                tokenized_documents
            )
        else:
            average_document_length = 0.0

        return cls(
            documents=documents,
            tokenized_documents=tokenized_documents,
            document_frequency=document_frequency,
            average_document_length=average_document_length,
            k1=k1,
            b=b,
        )

    def search(self, query: str, limit: int = 20) -> list[tuple[Document, float]]:
        query_terms = tokenize(query)
        if not query_terms or not self.documents:
            return []

        total_documents = len(self.documents)
        scored: list[tuple[Document, float]] = []

        for document, terms in zip(self.documents, self.tokenized_documents):
            term_counts = Counter(terms)
            document_length = len(terms) or 1
            score = 0.0
            for term in query_terms:
                if term not in term_counts:
                    continue
                frequency = self.document_frequency[term]
                idf = math.log(1 + (total_documents - frequency + 0.5) / (frequency + 0.5))
                term_frequency = term_counts[term]
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * document_length / self.average_document_length
                )
                score += idf * (term_frequency * (self.k1 + 1) / denominator)

            if score > 0:
                scored.append((document, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

