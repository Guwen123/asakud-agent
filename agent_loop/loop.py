from __future__ import annotations

import asyncio
import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

try:
    from .bootstrap import bootstrap
    from .config_loader import load_config, project_path
except ImportError:
    from bootstrap import bootstrap
    from config_loader import load_config, project_path

from db.runtime import RuntimeStore
from tools.registry import ToolRegistry
from memory.markdown import add_markdown_memory


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_markdown_memory(config: dict) -> str:
    chunks: list[str] = []
    for item in config["memory"]["markdown_files"]:
        path = project_path(item["path"])
        if path.exists():
            chunks.append(f"\n# {path.relative_to(project_path('.'))}\n")
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def remember_to_markdown(
    memory_id: str,
    content: str,
    section: str | None = None,
    reason: str | None = None,
) -> dict[str, str]:
    config = load_config()
    return add_markdown_memory(
        memory_id=memory_id,
        content=content,
        section=section,
        reason=reason,
        source="agent_loop",
        config=config,
    )


async def run_agent_once_async(user_input: str) -> str:
    bootstrap()
    config = load_config()

    store = RuntimeStore(
        project_path(config["paths"]["database"]),
        project_path(config["paths"]["schema"]),
    )
    store.initialize()

    session_id = str(uuid.uuid4())
    store.create_session(session_id=session_id, title="local session", started_at=now_iso())
    store.add_message(session_id=session_id, role="user", content=user_input)

    memory = load_markdown_memory(config)
    tools = ToolRegistry(config.get("tools", {}).get("enabled"))

    output = await asyncio.to_thread(
        invoke_chat_model,
        config,
        user_input,
        build_system_message(config, memory, tools.names()),
    )

    store.add_message(session_id=session_id, role="assistant", content=output)
    store.close()
    return output


def build_system_message(config: dict, markdown_memory: str, tool_names: list[str]) -> str:
    return "\n".join(
        [
            f"You are {config['agent']['name']}.",
            config["agent"].get("description", ""),
            "",
            "Long-term markdown memory:",
            markdown_memory or "No markdown memory loaded.",
            "",
            "Available tools:",
            ", ".join(tool_names) if tool_names else "No tools enabled.",
        ]
    )


def invoke_chat_model(
    config: dict[str, Any],
    user_message: str,
    system_message: str | None = None,
) -> str:
    model_config = config["model"]
    model = ChatOpenAI(
        model=model_config["name"],
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        temperature=model_config.get("temperature", 0.2),
        max_tokens=model_config.get("max_output_tokens"),
    )
    messages: list[BaseMessage] = []
    if system_message:
        messages.append(SystemMessage(content=system_message))
    messages.append(HumanMessage(content=user_message))
    response = model.invoke(messages)
    content = response.content
    if isinstance(content, str):
        return content
    return str(content)


def run_agent_once(user_input: str) -> str:
    return asyncio.run(run_agent_once_async(user_input))


if __name__ == "__main__":
    text = input("User> ")
    print(run_agent_once(text))
