from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

try:
    from .background import start_background_workers
    from .bootstrap import bootstrap
    from .config_loader import load_config
    from .workflow import AgentWorkflow
except ImportError:
    from background import start_background_workers
    from bootstrap import bootstrap
    from config_loader import load_config
    from workflow import AgentWorkflow


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def run_agent_once_async(user_input: str) -> dict[str, str]:
    bootstrap()
    config = load_config()
    start_background_workers(config)
    workflow = AgentWorkflow(config)
    workflow.build_workflow()
    app = workflow.compile()

    session_id = config.get("db", {}).get("default_session_id", "default")
    state = {
        "session_id": session_id,
        "original_user_input": user_input,
        "user_input": user_input,
        "messages": [HumanMessage(content=user_input)],
        "memory": {},
        "routing": {},
    }
    result = await asyncio.to_thread(app.invoke, state)
    return {
        "message": str(result.get("final_output", result.get("assistant_output", "")) or ""),
        "image_ref": str(result.get("final_meme_image_ref", "") or ""),
    }


def run_agent_once(user_input: str) -> dict[str, str]:
    return asyncio.run(run_agent_once_async(user_input))


if __name__ == "__main__":
    text = input("User> ")
    print(json.dumps(run_agent_once(text), ensure_ascii=False))
