from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import END, START, StateGraph

from compact import append_recent_summary_turn, load_recent_summary
from db.runtime import RuntimeStore

from .background import enqueue_memory_update
from .config_loader import load_config, project_path
from .nodes.core import AgentNodes
from .observability import finalize_trace, time_node


class AgentWorkflow:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_config()
        self.nodes = AgentNodes(self.config)
        self.graph: StateGraph | None = None

    def build_workflow(self) -> StateGraph:
        class WorkflowState(dict):
            messages: list[BaseMessage]
            session_id: str
            original_user_input: str
            user_input: str
            memory: dict[str, Any]
            routing: dict[str, Any]
            assistant_output: str
            final_output: str
            final_meme_image_ref: str
            db_snapshot: dict[str, Any]
            history_turn_count: int
            tool_step_count: int
            performance: dict[str, Any]

        workflow = StateGraph(WorkflowState)
        workflow.add_node("import_db", self._timed_node("import_db", RunnableLambda(self._import_db_state)))
        workflow.add_node("router_meme", self._timed_node("router_meme", self.nodes.get_router_meme_node()))
        workflow.add_node("md_memory", self._timed_node("md_memory", self.nodes.get_md_memory_node()))
        workflow.add_node("agent_model", self._timed_node("agent_model", self.nodes.get_agent_model_node()))
        workflow.add_node("tools", self._timed_node("tools", self.nodes.get_tool_node()))
        workflow.add_node("style", self._timed_node("style", self.nodes.get_style_node()))
        workflow.add_node("save_long_term", self._timed_node("save_long_term", RunnableLambda(self._save_long_term_memory)))
        workflow.add_node("trim_short_term", self._timed_node("trim_short_term", RunnableLambda(self._trim_short_term_memory)))
        workflow.add_node("export_db", self._timed_node("export_db", RunnableLambda(self._export_db_state)))
        workflow.add_node("save_skill", self._timed_node("save_skill", self.nodes.get_save_skill_node()))
        workflow.add_node("print_meme", self._timed_node("print_meme", self.nodes.get_print_meme_node(), finalize=True))

        workflow.add_edge(START, "import_db")
        workflow.add_edge("import_db", "router_meme")
        workflow.add_edge("router_meme", "md_memory")
        workflow.add_edge("md_memory", "agent_model")
        workflow.add_conditional_edges(
            "agent_model",
            self._has_tool_calls,
            {"tools": "tools", "agent_model": "agent_model", "done": "style"},
        )
        workflow.add_edge("tools", "agent_model")
        workflow.add_edge("style", "save_long_term")
        workflow.add_edge("save_long_term", "trim_short_term")
        workflow.add_edge("trim_short_term", "export_db")
        workflow.add_edge("export_db", "save_skill")
        workflow.add_edge("save_skill", "print_meme")
        workflow.add_edge("print_meme", END)

        self.graph = workflow
        return workflow

    def compile(self) -> Runnable:
        if self.graph is None:
            raise ValueError("Workflow not built. Call build_workflow() first.")
        return self.graph.compile()

    def _timed_node(self, name: str, runnable: Runnable, *, finalize: bool = False) -> Runnable:
        def _run(state: dict[str, Any]) -> dict[str, Any]:
            result = time_node(state, name, runnable.invoke)
            if finalize:
                finalize_trace(result)
                self._persist_performance_trace(result)
            return result

        return RunnableLambda(_run)

    def _has_tool_calls(self, state: dict[str, Any]) -> str:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return "done"
        if not bool(messages[-1].tool_calls):
            return "done"
        if self._tool_step_count(state) >= self._max_tool_steps():
            if state.get("tool_limit_reached"):
                state["assistant_output"] = "Tool step limit reached before a final answer could be produced."
                return "done"
            self._append_tool_limit_messages(state, messages[-1])
            state["tool_limit_reached"] = True
            return "agent_model"
        return "tools"

    def _import_db_state(self, state: dict[str, Any]) -> dict[str, Any]:
        store = self._new_store()
        store.initialize()
        session_id = str(state.get("session_id", "") or "")
        messages = list(state.get("messages", []))
        history_turn_count = 0
        if session_id:
            history_turn_count = store.count_messages(session_id=session_id, role="user")
            imported: list[BaseMessage] = []
            recent_summary = load_recent_summary(self.config)
            if recent_summary:
                imported.append(
                    HumanMessage(
                        content=(
                            "[RECENT_SUMMARY]\n"
                            "This is compressed prior conversation context, not a new user request.\n\n"
                            f"{recent_summary}"
                        )
                    )
                )
            if imported:
                messages = imported
        user_input = str(state.get("user_input", "") or "")
        if user_input and (not messages or not isinstance(messages[-1], HumanMessage) or messages[-1].content != user_input):
            messages.append(HumanMessage(content=user_input))
        state["messages"] = messages
        state["history_turn_count"] = history_turn_count
        state["tool_step_count"] = int(state.get("tool_step_count", 0) or 0)
        state["db_snapshot"] = {
            "sessions": [record.id for record in store.list_sessions(limit=5)],
            "history_loaded": 0,
            "history_dropped": 0,
            "recent_summary_loaded": bool(load_recent_summary(self.config)),
        }
        store.close()
        return state

    def _export_db_state(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = str(state.get("original_user_input", state.get("user_input", "")) or "")
        output = str(state.get("assistant_output", "") or "")
        store = self._new_store()
        store.initialize()
        try:
            session_id = str(state.get("session_id", "") or "")
            if session_id:
                store.create_session(session_id=session_id, title="workflow session")
                if user_input:
                    store.add_message(session_id=session_id, role="user", content=user_input)
                if output:
                    store.add_message(session_id=session_id, role="assistant", content=output)
        finally:
            store.close()
        if user_input or output:
            summary_update = append_recent_summary_turn(self.config, user_input, output)
            memory = dict(state.get("memory", {}) or {})
            memory["recent_summary"] = {
                "path": summary_update.path,
                "token_count": summary_update.token_count,
                "line_count": summary_update.line_count,
                "compacted": summary_update.compacted,
                "error": summary_update.error,
            }
            state["memory"] = memory
        return state

    def _save_long_term_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = str(state.get("user_input", "") or "")
        assistant_output = str(state.get("assistant_output", "") or "")
        if not user_input or not assistant_output:
            return state

        memory = dict(state.get("memory", {}) or {})
        memory["memory_worker"] = enqueue_memory_update(
            self.config,
            "long_term_update",
            {
                "session_id": str(state.get("session_id", "") or ""),
                "session_turn_count": int(state.get("history_turn_count", 0) or 0) + 1,
                "user_input": user_input,
                "assistant_output": assistant_output,
            },
        )
        state["memory"] = memory
        return state

    def _trim_short_term_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        # DB messages are append-only raw dialogue records. RECENT_SUMMARY is the
        # prompt-facing compacted conversation context.
        return state

    def _new_store(self) -> RuntimeStore:
        db_config = self.config.setdefault("db", {})
        db_config.setdefault("database", self.config["paths"]["database"])
        db_config.setdefault("schema", self.config["paths"]["schema"])
        return RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))

    def _persist_performance_trace(self, state: dict[str, Any]) -> None:
        trace = state.get("performance")
        if not isinstance(trace, dict):
            return
        store = self._new_store()
        try:
            store.initialize()
            store.add_performance_trace(trace)
            state["performance_persisted"] = True
        except Exception as exc:
            # Observability persistence must never break the user-facing answer.
            state["performance_persist_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            store.close()

    def _max_tool_steps(self) -> int:
        try:
            return max(int(self.config.get("loop", {}).get("max_steps", 30) or 30), 1)
        except (TypeError, ValueError):
            return 30

    @staticmethod
    def _tool_step_count(state: dict[str, Any]) -> int:
        try:
            return int(state.get("tool_step_count", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _append_tool_limit_messages(self, state: dict[str, Any], ai_message: AIMessage) -> None:
        messages = list(state.get("messages", []))
        payload = {
            "error": "tool_step_limit_reached",
            "max_steps": self._max_tool_steps(),
            "instruction": "Stop calling tools. Produce the best final answer from the information already available.",
        }
        for call in ai_message.tool_calls or []:
            messages.append(
                ToolMessage(
                    content=json.dumps(payload, ensure_ascii=False),
                    tool_call_id=str(call.get("id", "")),
                )
            )
        state["messages"] = messages
