# Sakuro Agent

This scaffold is driven by the root Markdown configuration file:

```text
agent.config.md
```

Run bootstrap to create memory Markdown files, SQLite schema, the session database, tool folders, and configured skill folders:

```powershell
python agent_loop\bootstrap.py
```

Run the always-on FastAPI service:

```powershell
python main.py
```

Useful endpoints:

- `GET /health`
- `POST /chat`
- `POST /workflow/chat`
- `GET /tools`
- `POST /tools/{tool_name}/run`
- `GET /memory/markdown`
- `POST /memory/markdown`
- `POST /memory/route-storage`

The important idea is that generated runtime files are not hard-coded by hand. They are described in the fenced `json` block inside `agent.config.md`.

## Flow

```text
agent.config.md
  -> agent_loop/bootstrap.py
  -> memory/*.md
  -> db/session_memory.schema.sql
  -> db/session_memory.db
  -> tools/
  -> skills/*/SKILL.md
```

## Files

- `agent.config.md`: root Markdown configuration for model, memory, database, loop, and skills.
- `agent_loop/bootstrap.py`: reads the root config and creates configured files.
- `agent_loop/config_loader.py`: shared config loader.
- `db/runtime/`: SQLite runtime store for sessions, messages, memory events, scheduled tasks, and skill runs.
- `db/langchain/`: LangChain `BaseChatMessageHistory` backed by SQLite.
- `db/schemas/`: database record classes.
- `db/utils/`: database JSON and id helpers.
- `agent_loop/loop.py`: minimal loop that loads config and memory.
- `agent_loop/nodes.py`: LangGraph node management and tool integration.
- `agent_loop/workflow.py`: Agent workflow construction using LangGraph StateGraph.
- `memory/markdown/`: Markdown memory target discovery and write logic.
- `memory/routing/`: LLM-based storage routing.
- `memory/schemas/`: memory routing and Markdown memory data classes.
- `rag/`: RAG retrieval package split into schemas, offline index building, retrieval, routing, and utils.
- `main.py`: FastAPI service entrypoint for running the agent continuously.
- `tools/`: tool registry and built-in tools available to the agent.
- `http_client/`: async HTTP helpers and OpenAI-compatible model client.

## RAG

RAG is split by responsibility:

- `rag/index.py`: public `RagDocument`, `RagChunk`, and `build_chunks` entrypoint.
- `rag/retriever.py`: online retrieval entrypoint.
- `rag/schemas/`: document, retrieval result, and protocol types.
- `rag/offline/`: offline `RagSearchIndex` construction.
- `rag/retrieval/`: BM25, dense retrieval, direct retrieval, hybrid rerank, Cross-Encoder rerank, and RRF.
- `rag/routing/`: LLM route prompt and query router.
- `rag/utils/`: tokenization, document conversion, and math helpers.

## Tools

Tools use LangGraph/LangChain-compatible objects:

- Built-in tools are defined with `langchain_core.tools.tool`.
- `ToolRegistry` stores `BaseTool` instances.
- `ToolRegistry.to_tool_node()` returns a `langgraph.prebuilt.ToolNode`.

## LangGraph Workflows

The agent supports LangGraph-based workflows for complex agent interactions:

- `agent_loop/nodes.py`: `AgentNodes` class manages LangGraph nodes including tool nodes, agent nodes, memory nodes, and routing nodes.
- `agent_loop/workflow.py`: `AgentWorkflow` class builds StateGraph workflows with conditional edges and state management.
- `POST /workflow/chat`: New endpoint for LangGraph-powered conversations with configurable workflow types ("basic" or "advanced").

Workflow types:
- **Basic**: Simple agent -> tools -> end flow
- **Advanced**: Includes memory management and routing decisions

## Rule

To add a new Markdown memory file or skill, edit `agent.config.md`, then run bootstrap again.
