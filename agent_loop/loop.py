from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

try:
    from .bootstrap import bootstrap
    from .config_loader import load_config
    from .workflow import AgentWorkflow
except ImportError:
    from bootstrap import bootstrap
    from config_loader import load_config
    from workflow import AgentWorkflow


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


async def run_agent_once_async(user_input: str) -> str:
    bootstrap()
    config = load_config()
    workflow = AgentWorkflow(config)
    workflow.build_workflow()
    app = workflow.compile()

    session_id = config.get("db", {}).get("default_session_id", "default")
    state = {
        "session_id": session_id,
        "user_input": user_input,
        "messages": [HumanMessage(content=user_input)],
        "memory": {},
        "routing": {},
        "rag_index": None,
    }
    result = await asyncio.to_thread(app.invoke, state)
    return str(result.get("assistant_output", "") or "")


def run_agent_once(user_input: str) -> str:
    return asyncio.run(run_agent_once_async(user_input))


if __name__ == "__main__":
    text = input("User> ")
    print(run_agent_once(text))
