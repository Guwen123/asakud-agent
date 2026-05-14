from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkdownMemoryTarget:
    id: str
    path: Path
    title: str
    sections: list[str]

