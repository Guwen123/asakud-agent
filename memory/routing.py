from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StorageRouteDecision:
    should_store: bool
    destination: str
    memory_id: str | None
    section: str | None
    reason: str
    content: str

    @property
    def should_write_markdown(self) -> bool:
        return self.memory_id is not None

    @property
    def should_write_rag(self) -> bool:
        return self.destination == "rag"


def route_storage_with_llm(
    content: str,
    route_llm: Any,
    context: str = "",
    config: dict[str, Any] | None = None,
) -> StorageRouteDecision:
    if not content.strip():
        return StorageRouteDecision(False, "none", None, None, "empty content", content)

    _ = route_llm, context, config
    return StorageRouteDecision(
        should_store=True,
        destination="project_memory",
        memory_id="project",
        section=None,
        reason="default storage route",
        content=content.strip(),
    )

