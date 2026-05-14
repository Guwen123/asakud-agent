from __future__ import annotations

from pathlib import Path

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from db.runtime import RuntimeStore


class SQLiteChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str, database_path: Path, schema_path: Path) -> None:
        self.session_id = session_id
        self.store = RuntimeStore(database_path=database_path, schema_path=schema_path)
        self.store.initialize()
        self.store.create_session(session_id=session_id)

    @property
    def messages(self) -> list[BaseMessage]:
        return [
            record_to_message(record.role, record.content)
            for record in self.store.get_messages(self.session_id)
        ]

    def add_message(self, message: BaseMessage) -> None:
        self.store.add_message(
            session_id=self.session_id,
            role=message_to_role(message),
            content=message.content if isinstance(message.content, str) else str(message.content),
            metadata={"type": message.type},
        )

    def clear(self) -> None:
        self.store.clear_messages(self.session_id)


def message_to_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, ToolMessage):
        return "tool"
    return message.type


def record_to_message(role: str, content: str) -> BaseMessage:
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="stored-tool-call")
    return SystemMessage(content=content)

