# asakud-agent

`asakud-agent` is a local long-running Agent system built with LangGraph, LangChain, FastAPI, SQLite, Redis hot memory, Markdown cold memory, executable skills, style layers, and browser-capable tools.

`asakud-agent` 是一个本地长运行智能体系统，核心包含 LangGraph 主流程、LangChain 模型调用、FastAPI 服务、SQLite 会话记录、Redis 热记忆、Markdown 冷记忆、可执行 Skill、独立 Style 层以及浏览器检索工具。

## Overview

This project is designed as a persistent assistant service rather than a one-shot script. It can receive NapCat messages, maintain memory, call tools, run generated skills, rewrite final responses through style packages, and expose a React dashboard for runtime observation and package management.

本项目不是一次性脚本，而是一个可持续运行的本地 Agent 服务。它可以接收 NapCat 消息、维护记忆、调用工具、运行生成的 Skill、通过 Style 包统一最终语气，并提供 React 可视化面板用于查看运行状态和管理 Skill / Style。

## Current Workflow

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

Prompt order for the main model:

```text
B1: static system prompt + cold Markdown memory
B2: Redis hot memory
A: RECENT_SUMMARY
C: current question
```

The main workflow no longer uses a separate workflow router for tool or memory decisions. Tool use is handled by model tool-calling, and cold memory is loaded in a stable order to improve KV-cache friendliness.

主流程不再使用额外的工具 / 记忆路由器。工具调用交给模型 tool-calling 决策，冷记忆按固定顺序加载，以尽量提升 KV-cache 命中稳定性。

## Features

- LangGraph-based main workflow with explicit node ordering.
- FastAPI service runtime with NapCat callback and send-message endpoints.
- SQLite append-only raw conversation history plus `memory/RECENT_SUMMARY.md` prompt context.
- Markdown cold memory: `MEMORY.md`, `SELF.md`, `CORE.md`, `PENDING.md`.
- Redis hot memory for staged memory updates before cold Markdown writes.
- Playwright-powered `fetch_web` tool/sub-agent for web search, browsing, extraction, and summarization.
- Executable Skill system with `SKILL.md`, `reference/`, optional `scripts/`, `entry`, and `skill.config.md`.
- Independent Style system under `styles/`, with `styles/style.config.md` recording style type and source.
- Async background workers for long-term memory updates and skill building.
- React dashboard for Agent/computer status, Skill list/upload, and Style list/upload.

## Project Structure

```text
asakud-agent/
|-- main.py                         # FastAPI entrypoint and dashboard API
|-- agent.config.md                 # Runtime configuration
|-- agent_loop/                     # Main LangGraph workflow and nodes
|-- compact/                        # RECENT_SUMMARY loading/appending/compaction
|-- db/                             # SQLite schema and runtime store
|-- memory/                         # Cold memory and forgetting/hot-store helpers
|-- memory_worker/                  # Async memory update sub-agent
|-- skill_builder/                  # Async skill generation sub-agent
|-- skill_runner/                   # Skill execution sub-agent
|-- style_runner/                   # Final response style sub-agent
|-- prompts/                        # Prompt templates
|-- tools/                          # Tool registry, fetch_web, MCP tools
|-- skills/                         # Executable skill registry and imported skills
|-- styles/                         # Style registry and style packages
|-- frontend/                       # React dashboard
`-- meme/                           # Meme metadata and image storage
```

## Quick Start

### Backend

```powershell
pip install -r requirements.txt
python agent_loop\bootstrap.py
python main.py
```

If you need browser automation:

```powershell
playwright install chromium
```

### Frontend Dashboard

```powershell
cd frontend
npm install
npm run dev
```

The dashboard calls `http://127.0.0.1:8000` by default. If the backend runs elsewhere, set `VITE_API_BASE`.

## Configuration

Runtime configuration lives in the fenced JSON block inside `agent.config.md`.

运行配置位于 `agent.config.md` 的 JSON 代码块中。

Sensitive values can be written as environment placeholders:

```json
{
  "model": {
    "api_key": "${MIMO_API_KEY}"
  },
  "napcat": {
    "token": "${NAPCAT_TOKEN}"
  }
}
```

If the environment variable is not set, the original placeholder text is kept. This keeps local development compatible while allowing safer deployment configuration.

## API

- `POST /getMessage`: receive NapCat callback messages.
- `POST /sendMessage`: send outbound NapCat messages.
- `GET /api/dashboard/status`: read Agent/computer/runtime status.
- `GET /api/dashboard/skills`: list registered executable skills.
- `POST /api/dashboard/skills/upload`: upload a Skill zip package.
- `GET /api/dashboard/styles`: list response styles.
- `POST /api/dashboard/styles/upload`: upload a Style zip package.

## Skills

Skills are executable task packages. A full skill may contain:

```text
SKILL.md
skill.json
reference/
scripts/
```

`skills/skill.config.md` records registered skills. The main Agent can call `run_skill` during the normal tool loop. `SkillRunnerAgent` executes a script entry first when available; otherwise it runs an LLM sub-agent with enabled tools such as `fetch_web`.

Skill 是可执行任务包，可以包含提示词、参考资料和可选脚本。主流程会在工具循环中调用 `run_skill`，由 `SkillRunnerAgent` 独立完成任务，再把结果交回主流程进行统一输出与风格处理。

## Styles

Styles are final response rewrite packages and are separate from executable skills.

```text
styles/
|-- style.config.md
`-- atri/
    |-- SKILL.md
    |-- soul.md
    |-- limit.md
    `-- resource/
```

`styles/style.config.md` records each style's `id`, `name`, `type`, `path` or `guide`, and `source`. ATRI is now a Style package, not a Skill package.

Style 只负责最终语气改写，不参与工具调用和任务执行。ATRI 已从 `skills/` 拆出，放入 `styles/atri/`。

## Why No Nginx Yet?

Nginx is not required for the current local development architecture:

- FastAPI serves the backend API directly on `127.0.0.1:8000`.
- Vite serves the React dashboard during development on `127.0.0.1:5173`.
- The Agent is intended to run locally with NapCat and local tools, so a reverse proxy is optional.

Use Nginx when deploying beyond local development:

- Serve `frontend/dist` as static files.
- Reverse proxy `/api/*`, `/getMessage`, and `/sendMessage` to FastAPI.
- Terminate HTTPS.
- Add compression, caching, and access control.

For local iteration, adding Nginx now would increase configuration complexity without improving the Agent logic.

当前本地开发阶段不需要 Nginx：FastAPI 和 Vite 已经能分别承担后端 API 与前端开发服务。只有在部署到服务器、需要 HTTPS、静态资源托管、反向代理、压缩缓存或访问控制时，才建议加入 Nginx。

## Resume Highlights

- Built a LangGraph-based local long-running Agent with memory, tools, style finalization, and async sub-agents.
- Implemented `fetch_web` as a focused Playwright web-research sub-agent, reducing main-context token overhead by isolating search/browse/extract/summarize tasks.
- Designed an executable Skill system with asynchronous skill generation, package registration, optional scripts, references, and tool-enabled execution.
- Split response Style into an independent package system with a final style sub-agent, enabling persona/tone control without polluting task skills.
- Added a React dashboard for visualizing Agent/computer status and managing Skill/Style zip packages.
