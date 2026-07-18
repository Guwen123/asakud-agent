from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agent_loop.config_loader import load_config
from llm.factory import build_route_model

from .tools import open_page, click_element, get_page_content, extract_info


FETCH_WEB_SYSTEM_PROMPT = """You are a focused web-research sub-agent.

Your operating procedure:
1. Start by searching the user's topic with `open_page` using a natural-language query unless the user already provided a specific target URL.
2. Inspect the search results or current page with `get_page_content`.
3. Use `click_element` to open the most relevant result or navigate deeper when needed.
4. After reaching the target content, use `extract_info` on the most relevant section to gather evidence.
5. Only after you have enough evidence, answer the user directly in natural language without calling more tools.

Rules:
- Prefer searching first, then clicking into results, then extracting, then summarizing.
- Do not answer before you have inspected page content unless the request is trivial.
- Keep the final answer concise and factual.
- If the information is uncertain or incomplete, say so clearly.
"""


class FetchWebAgent:
    def __init__(self, max_steps=10):
        tools = [open_page, click_element, get_page_content, extract_info]
        config = load_config()
        llm = build_route_model(
            config,
            overrides={"name": "mimo-v2.5", "temperature": 0.0},
        ).bind_tools(tools)

        class State(TypedDict):
            messages: Annotated[list[BaseMessage], add_messages]
            final_result: str
            step_count: int

        def call_model(state):
            response = llm.invoke(state["messages"])
            return {
                "messages": [response],
                "step_count": int(state.get("step_count", 0)) + 1,
            }

        tool_node = ToolNode(tools)

        def should_continue_from_agent(state):
            messages = state.get("messages", [])
            if not messages:
                return "finish"
            last_msg = messages[-1]
            step_count = int(state.get("step_count", 0))
            if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
                if step_count >= max_steps:
                    return "finish"
                return "tools"
            return "finish"

        def finish(state):
            messages = state.get("messages", [])
            last_ai_message = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
            last_msg = last_ai_message or (messages[-1] if messages else None)
            content = getattr(last_msg, "content", "") if last_msg is not None else ""
            if isinstance(content, str):
                state["final_result"] = content
            else:
                state["final_result"] = str(content)
            return state

        workflow = StateGraph(State)

        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        workflow.add_node("finish", finish)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges("agent", should_continue_from_agent, {
            "tools": "tools",
            "finish": "finish",
        })
        workflow.add_edge("tools", "agent")
        workflow.add_edge("finish", END)

        self.workflow = workflow.compile()

    def run(self, query):
        initial_state = {
            "messages": [
                SystemMessage(content=FETCH_WEB_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            "final_result": "",
            "step_count": 0,
        }
        final_state = self.workflow.invoke(initial_state)
        return final_state["final_result"]
