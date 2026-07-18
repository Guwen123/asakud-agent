# asakud-agent

`asakud-agent` is a local long-running Agent system built with LangGraph, LangChain, FastAPI, SQLite, Redis hot memory, Markdown cold memory, executable skills, style packages, MCP tools, and browser-capable web search.

`asakud-agent` 是一个本地长期运行的智能体系统，基于 LangGraph / LangChain / FastAPI 构建，支持会话记忆、网页检索、MCP 工具、可执行 Skill、最终语气 Style、前端状态面板以及异步记忆和 Skill 构建。

## Overview

The project is designed as a persistent assistant service rather than a one-shot script. It can receive NapCat messages, maintain memory, call tools, run reusable skills, rewrite final responses through style packages, and expose a React dashboard for runtime management.

本项目不是一次性脚本，而是一个长期运行的本地 Agent 服务。它可以接收 NapCat 消息，维护长期/短期记忆，调用工具和子 Agent，执行可复用 Skill，并通过 Style 子流程统一最终回复语气。

## Workflow

```text
incoming message
  -> import_db
  -> router_meme
  -> md_memory
  -> agent_model
  -> tools / run_skill loop
  -> style
  -> save_long_term
  -> trim_short_term
  -> export_db
  -> save_skill
  -> print_meme
  -> response
```

Main prompt order:

```text
B1: static system prompt + cold Markdown memory
B2: Redis hot memory
A: RECENT_SUMMARY
C: current question
```

主流程负责理解用户意图、调用普通工具或 `run_skill`、维护记忆和输出草稿；StyleRunner 只负责最终语气改写；SkillRunner 是独立子流程。

## Features

- LangGraph main workflow with explicit node order and tool loop limit.
- FastAPI runtime with NapCat callback/send endpoints and dashboard APIs.
- SQLite append-only raw conversation history plus `memory/RECENT_SUMMARY.md` prompt-facing summary.
- Markdown cold memory: `MEMORY.md`, `SELF.md`, `CORE.md`, `PENDING.md`.
- Redis hot memory for staged updates before cold Markdown writes.
- Playwright-powered `fetch_web` tool/sub-agent for search, browsing, extraction, and summarization.
- MCP server management from the React dashboard with dynamic remote tool loading.
- Executable Skill packages with `SKILL.md`, `skill.json`, `reference/`, optional `scripts/`, and `entry`.
- Async `skill_builder` that can generate reusable Skill packages from high-value completed tasks.
- Independent Style packages under `styles/`, with ATRI as the default final response style.
- React dashboard for Agent/computer status, Skill/Style upload, MCP server setup, and model settings.

## Project Structure

```text
asakud-agent/
|-- main.py                         # FastAPI entrypoint and dashboard API
|-- agent.config.md                 # Runtime configuration
|-- agent_loop/                     # Main LangGraph workflow and nodes
|-- compact/                        # RECENT_SUMMARY loading/appending/compaction
|-- db/                             # SQLite schema and runtime store
|-- memory/                         # Cold memory, hot store, forgetting helpers
|-- memory_worker/                  # Async memory update sub-agent
|-- skill_builder/                  # Async skill generation sub-agent
|-- skill_runner/                   # Skill execution sub-agent
|-- style_runner/                   # Final response style sub-agent
|-- prompts/                        # Prompt templates
|-- tools/                          # Tool registry, fetch_web, MCP tools
|-- skills/                         # Skill registry, templates, generated/imported skills
|-- styles/                         # Style registry and style packages
|-- frontend/                       # React dashboard
`-- meme/                           # Meme metadata and image storage
```

## Quick Start

Backend:

```powershell
pip install -r requirements.txt
python agent_loop\bootstrap.py
python main.py
```

Browser automation:

```powershell
playwright install chromium
```

Frontend dashboard:

```powershell
cd frontend
npm install
npm run dev
```

The dashboard calls `http://127.0.0.1:8000` by default. Set `VITE_API_BASE` if the backend runs elsewhere.

## Configuration

Runtime configuration lives in the fenced JSON block inside `agent.config.md`.

The model config is intentionally limited to three roles:

```json
{
  "main_model": {
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2.5-pro"
  },
  "route_model": {
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2.5"
  },
  "multimodal_model": {
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2-omni"
  }
}
```

You can also update `base_url`, `api_key`, model name, temperature, and output token limits from the dashboard Settings page.

敏感值可以写成环境变量占位符，例如 `${MIMO_API_KEY}`。如果环境变量不存在，占位符会原样保留，方便本地开发和部署环境分离。

## Skills

Skills are reusable executable task packages. A complete Skill may contain:

```text
SKILL.md
skill.json
reference/
scripts/
```

Execution model:

```text
Main Agent
  -> decides whether to call run_skill
SkillRunnerAgent
  -> reads SKILL.md + references with an LLM
  -> if the skill has an entry, exposes only run_skill_script to the sub-LLM
  -> the script owns fetch_web/MCP calls through context["run_tool"]
  -> if there is no script, the sub-LLM may directly use enabled project tools
```

This keeps the boundary clear: the LLM reads the Skill instructions and decides whether to run the executable script; scripted web/MCP behavior lives inside the script.

`skill_builder` runs asynchronously after a successful main-flow response. It receives the completed task, existing skill summaries, enabled tools, and local templates from `skills/_templates`, then may generate a new package under `skills/generated/`.

## Styles

Styles are final response rewrite packages, separate from executable Skills.

```text
styles/
|-- style.config.md
`-- atri/
    |-- SKILL.md
    |-- soul.md
    |-- limit.md
    `-- resource/
```

ATRI is stored as a Style package, not a Skill package. The main task result is produced first, then StyleRunner rewrites the final answer.

## MCP Tools

MCP is disabled by default. The bundled `local-mcp-example` is only a disabled example and will not work unless a real MCP HTTP / Streamable HTTP gateway is running at that address.

Supported modes:

- `mcp-jsonrpc`: MCP JSON-RPC / Streamable HTTP endpoint, usually ending in `/mcp`.
- `simple-http`: REST-like gateway using `/tools` and `/tools/call`.

Users can add real MCP servers from the dashboard. The backend writes the server into `agent.config.md`, enables `mcp`, probes tools, and exposes remote tools with names such as `mcp.my-mcp.search`.

## Dashboard API

- `GET /api/dashboard/status`: Agent/computer/runtime status.
- `GET /api/dashboard/models`: read `main_model`, `route_model`, and `multimodal_model`.
- `PUT /api/dashboard/models`: update model `base_url`, `api_key`, name, temperature, and token limits.
- `GET /api/dashboard/skills`: list registered skills.
- `POST /api/dashboard/skills/upload`: upload a Skill zip package.
- `GET /api/dashboard/styles`: list response styles.
- `POST /api/dashboard/styles/upload`: upload a Style zip package.
- `GET /api/dashboard/mcp`: list MCP servers.
- `POST /api/dashboard/mcp/servers`: add or update an MCP server.
- `GET /api/dashboard/mcp/servers/{server_name}/tools`: probe MCP tools.

## Resume Highlights

- Built a LangGraph-based local long-running Agent with memory, tools, executable skills, style finalization, and async sub-agents.
- Implemented `fetch_web` as a Playwright-based web-research capability, isolating search/browse/extract/summarize tasks from the main workflow to reduce token interference and main-context overhead.
- Designed an executable Skill system where the main Agent routes tasks, SkillRunner reads `SKILL.md` and references, and scripts own `fetch_web/MCP` calls through a controlled runtime context.
- Added an async `skill_builder` sub-agent with local templates to generate reusable Skill packages containing `SKILL.md`, references, and optional executable scripts.
- Implemented Redis hot memory plus Markdown cold memory with RECENT_SUMMARY compaction to balance personalization, persistence, and KV-cache friendliness.
- Added a React dashboard for runtime status, Skill/Style package uploads, MCP server management, and user-configurable LLM API/base URL settings.

## Notes

Nginx is not required for local development. Use it only when deploying the dashboard and FastAPI service behind HTTPS, static-file serving, or reverse proxy rules.
