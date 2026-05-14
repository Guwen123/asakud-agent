from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .documents import RagChunk


RouteName = Literal["direct", "hybrid_rerank"]


@dataclass(frozen=True)
class RetrievalResult:
    chunk: RagChunk
    score: float
    source: str = "unknown"


@dataclass(frozen=True)
class RoutedRetrievalResult:
    route: RouteName
    results: list[RetrievalResult]

