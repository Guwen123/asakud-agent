from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


StorageDestination = Literal[
    "none",
    "session_memory",
    "user_memory",
    "project_memory",
    "decision_memory",
    "scheduled_task",
    "rag",
]


DESTINATION_TO_MEMORY_ID: dict[StorageDestination, str | None] = {
    "none": None,
    "session_memory": None,
    "user_memory": "user",
    "project_memory": "project",
    "decision_memory": "decisions",
    "scheduled_task": "scheduled",
    "rag": None,
}


@dataclass(frozen=True)
class StorageRouteDecision:
    should_store: bool
    destination: StorageDestination
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

