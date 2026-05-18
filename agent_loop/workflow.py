from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import END, START, StateGraph

from db.runtime import RuntimeStore
from memory.markdown import add_markdown_memory

from .config_loader import load_config, project_path
from .model_factory import build_chat_model
from .nodes import AgentNodes


class AgentWorkflow:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_config()
        self.nodes = AgentNodes(self.config)
        self.graph: StateGraph | None = None

    def build_workflow(self) -> StateGraph:
        class WorkflowState(dict):
            messages: list[BaseMessage]
            session_id: str
            user_input: str
            memory: dict[str, Any]
            routing: dict[str, Any]
            rag_index: Any
            assistant_output: str
            db_snapshot: dict[str, Any]

        workflow = StateGraph(WorkflowState)

        workflow.add_node("import_db", RunnableLambda(self._import_db_state))
        workflow.add_node("router", self.nodes.get_router_node())
        workflow.add_node("md_memory", self.nodes.get_md_memory_node())
        workflow.add_node("rag_memory", self.nodes.get_rag_retrieval_memory_node())
        workflow.add_node("agent_model", self.nodes.get_agent_model_node())
        workflow.add_node("tools", self.nodes.get_tool_node())
        workflow.add_node("save_long_term", RunnableLambda(self._save_long_term_memory))
        workflow.add_node("trim_short_term", RunnableLambda(self._trim_short_term_memory))
        workflow.add_node("export_db", RunnableLambda(self._export_db_state))

        workflow.add_edge(START, "import_db")
        workflow.add_edge("import_db", "router")
        workflow.add_edge("router", "md_memory")
        workflow.add_edge("md_memory", "rag_memory")
        workflow.add_edge("rag_memory", "agent_model")
        workflow.add_conditional_edges(
            "agent_model", 
            self._has_tool_calls, 
            {"tools": "tools", "done": "save_long_term"}
            )
        workflow.add_edge("tools", "agent_model")
        workflow.add_edge("save_long_term", "trim_short_term")
        workflow.add_edge("trim_short_term", "export_db")
        workflow.add_edge("export_db", END)

        self.graph = workflow
        return workflow

    def compile(self) -> Runnable:
        if self.graph is None:
            raise ValueError("Workflow not built. Call build_workflow() first.")
        return self.graph.compile()

    def _has_tool_calls(self, state: dict[str, Any]) -> str:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return "done"
        return "tools" if bool(messages[-1].tool_calls) else "done"

    def _import_db_state(self, state: dict[str, Any]) -> dict[str, Any]:
        store = self._new_store()
        store.initialize()

        session_id = str(state.get("session_id", "") or "")
        if session_id:
            records = store.get_messages(session_id=session_id, limit=20)
            if records:
                imported: list[BaseMessage] = []
                for item in records:
                    if item.role == "user":
                        imported.append(HumanMessage(content=item.content))
                    elif item.role == "assistant":
                        imported.append(AIMessage(content=item.content))
                if imported:
                    state["messages"] = imported

        state["db_snapshot"] = {
            "sessions": [record.id for record in store.list_sessions(limit=5)],
        }
        store.close()
        return state

    def _export_db_state(self, state: dict[str, Any]) -> dict[str, Any]:
        store = self._new_store()
        store.initialize()

        session_id = str(state.get("session_id", "") or "")
        if session_id:
            store.create_session(session_id=session_id, title="workflow session")
            user_input = str(state.get("user_input", "") or "")
            if user_input:
                store.add_message(session_id=session_id, role="user", content=user_input)
            output = str(state.get("assistant_output", "") or "")
            if output:
                store.add_message(session_id=session_id, role="assistant", content=output)
        store.close()
        return state

    def _save_long_term_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = str(state.get("user_input", "") or "")
        assistant_output = str(state.get("assistant_output", "") or "")
        if not user_input or not assistant_output:
            return state
        model = build_chat_model(self.config, overrides={"temperature": 0.0, "max_output_tokens": 800})
        prompt = (
            "你是记忆路由器。根据这轮对话抽取长期记忆，返回 JSON："
            '{"save_to_rag":bool,"memory_habit":"","self_update":""}。'
            "不需要保存就留空字符串。memory_habit写入MEMORY.md，self_update写入SELF.md。"
        )
        response = model.invoke([SystemMessage(content=prompt), HumanMessage(content=json.dumps({"user": user_input, "assistant": assistant_output}, ensure_ascii=False))])
        decision = self._parse_json_response(self._extract_text(response))
        memory_habit = str(decision.get("memory_habit", "") or "").strip()
        self_update = str(decision.get("self_update", "") or "").strip()
        save_to_rag = bool(decision.get("save_to_rag", False))
        if save_to_rag and (memory_habit or self_update):
            rag_path = project_path(self.config["paths"].get("rag_memory_file", "rag/data/long_term_memory.jsonl"))
            rag_path.parent.mkdir(parents=True, exist_ok=True)
            row = {"user": user_input, "assistant": assistant_output, "memory_habit": memory_habit, "self_update": self_update}
            with rag_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if memory_habit:
            add_markdown_memory("project", memory_habit, section="长期说明", reason="session_memory_route", source="memory_router", config=self.config)
        if self_update:
            add_markdown_memory("self", self_update, section="工作方式", reason="session_self_reflection", source="memory_router", config=self.config)
        return state

    def _trim_short_term_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        session_id = str(state.get("session_id", "") or "")
        if not session_id:
            return state
        store = self._new_store()
        store.initialize()
        records = store.get_messages(session_id=session_id, limit=None)
        loop_cfg = self.config.get("loop", {})
        max_messages = int(loop_cfg.get("short_term_max_messages", 20))
        keep_recent = int(loop_cfg.get("short_term_keep_recent", 8))
        if len(records) <= max_messages or keep_recent >= len(records):
            store.close()
            return state
        old_records = records[:-keep_recent]
        recent_records = records[-keep_recent:]
        old_texts = [f"{r.role}: {r.content}" for r in old_records if r.role != "system"]
        if not old_texts:
            store.close()
            return state
        model = build_chat_model(self.config, overrides={"temperature": 0.0, "max_output_tokens": 600})
        summary_resp = model.invoke([SystemMessage(content="请总结以下历史消息，保留事实、偏好、未完成事项。输出简短中文摘要。"), HumanMessage(content="\n".join(old_texts))])
        summary = self._extract_text(summary_resp)
        store.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        store.conn.commit()
        store.add_message(session_id=session_id, role="system", content=f"[历史摘要]{summary}")
        for item in recent_records:
            store.add_message(session_id=session_id, role=item.role, content=item.content, created_at=item.created_at)
        store.close()
        return state

    def _new_store(self) -> RuntimeStore:
        db_config = self.config.setdefault("db", {})
        db_config.setdefault("database", self.config["paths"]["database"])
        db_config.setdefault("schema", self.config["paths"]["schema"])
        return RuntimeStore(
            project_path(db_config["database"]),
            project_path(db_config["schema"]),
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        content = getattr(response, "content", "")
        if isinstance(content, str):
            return content
        return str(content)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        raw = text.strip()
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
