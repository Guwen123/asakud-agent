from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from .config_loader import load_config
from .model_factory import build_chat_model
from memory.routing.parsers import extract_text, parse_json_response


SYSTEM_PROMPT = """你是 Sakuro Agent 的路由判定器。
你只输出一个 JSON 对象，用于决定下一步执行路径。
输出应包含：
- destination: agent 或 memory
- memory_source: markdown 或 rag
- rag_mode: direct 或 hybrid_rerank
- use_tool: true 或 false
- plan: 简要说明应该执行的步骤

如果消息需要使用长期知识或检索，memory_source 应该是 rag 或 markdown。
如果消息是普通对话或工具调用，destination 应该是 agent。
如果需要在 agent 中执行 Meme 相关工具，则 destination 仍然是 agent，use_tool 可以为 true。
"""


def _parse_route_response(response: Any) -> dict[str, Any]:
    text = extract_text(response)
    payload = parse_json_response(text)
    return {
        "destination": payload.get("destination", "agent").strip().lower(),
        "memory_source": payload.get("memory_source", "markdown").strip().lower(),
        "rag_mode": payload.get("rag_mode", "direct").strip().lower(),
        "use_tool": bool(payload.get("use_tool", False)),
        "plan": payload.get("plan", ""),
    }


def get_routing_node(config: dict | None = None) -> Runnable:
    """使用配置文件中的 LLM 来做路由判断。"""
    cfg = config or load_config()
    route_llm = build_chat_model(cfg, model_key="route_model")

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            state["routing"] = {
                "destination": "agent",
                "memory_source": "markdown",
                "rag_mode": "direct",
                "use_tool": False,
                "plan": "",
            }
            state["next"] = "agent"
            return state

        last_message = messages[-1]
        content = getattr(last_message, "content", None) or str(last_message)
        payload = {
            "content": content,
            "memory_source": "markdown",
            "rag_mode": "direct",
            "use_tool": False,
            "plan": "请根据用户输入生成下一步执行计划。",
        }

        response = route_llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])

        routing = _parse_route_response(response)
        if routing["destination"] not in {"agent", "memory"}:
            routing["destination"] = "agent"
        if routing["memory_source"] not in {"markdown", "rag"}:
            routing["memory_source"] = "markdown"
        if routing["rag_mode"] not in {"direct", "hybrid_rerank"}:
            routing["rag_mode"] = "direct"
        if routing["destination"] != "memory":
            routing["memory_source"] = "markdown"

        state["routing"] = routing
        state["next"] = routing["destination"]
        return state

    return RunnableLambda(_run)
