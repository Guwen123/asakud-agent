# asakud-agent

<p align="right">
  <a href="#english"><kbd>English</kbd></a>
  &nbsp;|&nbsp;
  <a href="#中文版本"><kbd>中文</kbd></a>
</p>

<a id="english"></a>

`asakud-agent` is a local long-running Agent system built around LangGraph, LangChain, FastAPI, Redis, SQLite, executable Skills, Style packages, MCP tools, and browser-capable web search.

The project is designed as a persistent assistant service rather than a one-shot script. It can receive NapCat messages, maintain long-term and short-term memory, call tools, run reusable Skills, rewrite final responses through Style packages, and expose a React dashboard for runtime management.

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

The main workflow handles user intent, normal tool calls, Skill routing, memory updates, and final orchestration. Dedicated sub-agents handle web research, memory updates, Skill building, Skill execution, and final style rewriting.

## Features

- LangGraph main workflow with explicit node order and tool loop limit.
- FastAPI runtime with NapCat callback/send endpoints and dashboard APIs.
- SQLite append-only raw conversation history plus `memory/RECENT_SUMMARY.md` prompt-facing summary.
- Markdown cold memory: `MEMORY.md`, `SELF.md`, `CORE.md`, and `PENDING.md`.
- Redis hot memory for staged memory updates before cold Markdown writes.
- Playwright-powered `fetch_web` sub-agent for search, browsing, extraction, and summarization.
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
|-- llm/                            # LLM factory for main/route/multimodal models
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
playwright install chromium
python agent_loop\bootstrap.py
python main.py
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

The LLM configuration is intentionally limited to three model roles:

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

This keeps the boundary clear: the LLM reads Skill instructions and decides whether to run the executable script; scripted web/MCP behavior lives inside the script.

`skill_builder` runs asynchronously after a successful main-flow response. It receives the completed task, existing Skill summaries, enabled tools, and local templates from `skills/_templates`, then may generate a new package under `skills/generated/`.

## Styles

Styles are final-response rewrite packages, separate from executable Skills.

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
- `GET /api/dashboard/skills`: list registered Skills.
- `POST /api/dashboard/skills/upload`: upload a Skill zip package.
- `GET /api/dashboard/styles`: list response Styles.
- `POST /api/dashboard/styles/upload`: upload a Style zip package.
- `GET /api/dashboard/mcp`: list MCP servers.
- `POST /api/dashboard/mcp/servers`: add or update an MCP server.
- `GET /api/dashboard/mcp/servers/{server_name}/tools`: probe MCP tools.

## Resume Highlights

- Built a LangGraph-based local long-running Agent with memory, tools, executable Skills, Style finalization, and async sub-agents.
- Implemented `fetch_web` as a Playwright-based web-research capability, isolating search/browse/extract/summarize tasks from the main workflow to reduce token interference and main-context overhead.
- Designed an executable Skill system where the main Agent routes tasks, SkillRunner reads `SKILL.md` and references, and scripts own `fetch_web/MCP` calls through a controlled runtime context.
- Added an async `skill_builder` sub-agent with local templates to generate reusable Skill packages containing `SKILL.md`, references, and optional executable scripts.
- Implemented Redis hot memory plus Markdown cold memory with RECENT_SUMMARY compaction to balance personalization, persistence, and KV-cache friendliness.
- Added a React dashboard for runtime status, Skill/Style package uploads, MCP server management, and user-configurable LLM API/base URL settings.

## Notes

Nginx is not required for local development. Use it only when deploying the dashboard and FastAPI service behind HTTPS, static-file serving, or reverse proxy rules.

<hr />

<a id="中文版本"></a>

<details>
<summary><strong>中文版本 / Click to switch to Chinese</strong></summary>

# asakud-agent 中文说明

`asakud-agent` 是一个本地长期运行的智能体系统，核心围绕 LangGraph、LangChain、FastAPI、Redis、SQLite、可执行 Skill、Style 包、MCP 工具以及具备浏览器能力的网页检索能力构建。

本项目不是一次性脚本，而是一个可持续运行的本地 Agent 服务。它可以接收 NapCat 消息，维护长期/短期记忆，调用工具，执行可复用 Skill，通过 Style 包统一最终回复语气，并提供 React Dashboard 管理运行状态。

## 工作流

```text
用户消息
  -> import_db
  -> router_meme
  -> md_memory
  -> agent_model
  -> tools / run_skill 循环
  -> style
  -> save_long_term
  -> trim_short_term
  -> export_db
  -> save_skill
  -> print_meme
  -> response
```

主提示词顺序：

```text
B1: 静态 system prompt + 冷 Markdown 记忆
B2: Redis 热记忆
A: RECENT_SUMMARY
C: 当前问题
```

主流程负责理解用户意图、调用普通工具或 `run_skill`、维护记忆以及编排最终输出。网页检索、记忆更新、Skill 构建、Skill 执行和最终语气改写都由独立子流程完成。

## 核心功能

- 基于 LangGraph 的主工作流，节点顺序清晰，并限制工具循环次数。
- FastAPI 运行时，支持 NapCat 回调/发送接口和 Dashboard API。
- SQLite 追加式保存原始对话记录，`memory/RECENT_SUMMARY.md` 用于本轮 prompt 可见的压缩摘要。
- Markdown 冷记忆：`MEMORY.md`、`SELF.md`、`CORE.md`、`PENDING.md`。
- Redis 热记忆：先暂存待写入记忆，满足条件后再异步写入 Markdown。
- 基于 Playwright 的 `fetch_web` 子 Agent，支持搜索、浏览、提取和总结。
- React Dashboard 支持配置 MCP Server，并动态加载远程工具。
- 可执行 Skill 包支持 `SKILL.md`、`skill.json`、`reference/`、可选 `scripts/` 和 `entry`。
- 异步 `skill_builder` 可以从高价值任务中自动生成可复用 Skill。
- `styles/` 下独立管理 Style 包，默认使用 ATRI 作为最终回复风格。
- React Dashboard 可查看 Agent/电脑状态，上传 Skill/Style，配置 MCP 和 LLM 模型参数。

## 项目结构

```text
asakud-agent/
|-- main.py                         # FastAPI 入口和 Dashboard API
|-- agent.config.md                 # 运行时配置
|-- llm/                            # 主模型/路由模型/多模态模型工厂
|-- agent_loop/                     # 主 LangGraph 工作流和节点
|-- compact/                        # RECENT_SUMMARY 加载、追加和压缩
|-- db/                             # SQLite schema 和运行时存储
|-- memory/                         # 冷记忆、热记忆、遗忘机制
|-- memory_worker/                  # 异步记忆更新子 Agent
|-- skill_builder/                  # 异步 Skill 生成子 Agent
|-- skill_runner/                   # Skill 执行子 Agent
|-- style_runner/                   # 最终回复风格子 Agent
|-- prompts/                        # Prompt 模板
|-- tools/                          # 工具注册、fetch_web、MCP 工具
|-- skills/                         # Skill 注册表、模板、生成/导入的 Skill
|-- styles/                         # Style 注册表和 Style 包
|-- frontend/                       # React Dashboard
`-- meme/                           # 表情包元数据和图片存储
```

## 快速启动

后端：

```powershell
pip install -r requirements.txt
playwright install chromium
python agent_loop\bootstrap.py
python main.py
```

前端 Dashboard：

```powershell
cd frontend
npm install
npm run dev
```

Dashboard 默认请求 `http://127.0.0.1:8000`。如果后端地址不同，可以设置 `VITE_API_BASE`。

## 配置

运行时配置位于 `agent.config.md` 的 fenced JSON 代码块中。

LLM 配置只保留三个模型角色：

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

你也可以在 Dashboard Settings 页面中修改 `base_url`、`api_key`、模型名、温度和输出 token 限制。

## Skills

Skill 是可复用的可执行任务包。一个完整 Skill 可以包含：

```text
SKILL.md
skill.json
reference/
scripts/
```

执行模型：

```text
Main Agent
  -> 判断是否调用 run_skill
SkillRunnerAgent
  -> 用 LLM 阅读 SKILL.md + references
  -> 如果 Skill 有 entry，只向子 LLM 暴露 run_skill_script
  -> 脚本通过 context["run_tool"] 自己调用 fetch_web/MCP
  -> 如果没有脚本，子 LLM 可以直接使用已启用的项目工具
```

这样可以保持边界清晰：LLM 负责阅读 Skill 说明并判断是否运行脚本；脚本型 Skill 的联网/MCP 行为封装在脚本内部。

`skill_builder` 会在主流程成功回复后异步运行。它会读取已完成任务、已有 Skill 摘要、已启用工具和 `skills/_templates` 下的本地模板，然后尝试在 `skills/generated/` 下生成新的 Skill 包。

## Styles

Style 是最终回复改写包，和可执行 Skill 分离。

```text
styles/
|-- style.config.md
`-- atri/
    |-- SKILL.md
    |-- soul.md
    |-- limit.md
    `-- resource/
```

ATRI 被保存为 Style，而不是 Skill。主流程先产出任务结果，再由 StyleRunner 统一改写最终语气。

## MCP 工具

MCP 默认关闭。内置的 `local-mcp-example` 只是禁用示例，除非你真的在对应地址启动 MCP HTTP / Streamable HTTP 网关，否则不会工作。

支持模式：

- `mcp-jsonrpc`：MCP JSON-RPC / Streamable HTTP 端点，通常以 `/mcp` 结尾。
- `simple-http`：REST 风格网关，使用 `/tools` 和 `/tools/call`。

用户可以从 Dashboard 添加真实 MCP Server。后端会写入 `agent.config.md`，启用 `mcp`，探测工具，并以 `mcp.my-mcp.search` 这类名字暴露远程工具。

## Dashboard API

- `GET /api/dashboard/status`：Agent、电脑、运行时状态。
- `GET /api/dashboard/models`：读取 `main_model`、`route_model`、`multimodal_model`。
- `PUT /api/dashboard/models`：更新模型 `base_url`、`api_key`、名称、温度和 token 限制。
- `GET /api/dashboard/skills`：列出已注册 Skill。
- `POST /api/dashboard/skills/upload`：上传 Skill zip 包。
- `GET /api/dashboard/styles`：列出回复 Style。
- `POST /api/dashboard/styles/upload`：上传 Style zip 包。
- `GET /api/dashboard/mcp`：列出 MCP Server。
- `POST /api/dashboard/mcp/servers`：添加或更新 MCP Server。
- `GET /api/dashboard/mcp/servers/{server_name}/tools`：探测 MCP 工具。

## 简历亮点

- 构建基于 LangGraph 的本地长期运行 Agent，集成记忆、工具、可执行 Skill、Style 终稿改写和异步子 Agent。
- 实现基于 Playwright 的 `fetch_web` 网页检索能力，将搜索/浏览/提取/总结任务从主流程隔离，减少无关上下文干扰和 token 消耗。
- 设计可执行 Skill 系统：主 Agent 负责任务路由，SkillRunner 阅读 `SKILL.md` 和 references，脚本通过受控 runtime context 调用 `fetch_web/MCP`。
- 实现异步 `skill_builder` 子 Agent，结合本地模板生成包含 `SKILL.md`、references 和可选脚本的可复用 Skill 包。
- 实现 Redis 热记忆 + Markdown 冷记忆 + RECENT_SUMMARY 压缩，在个性化、持久化和 KV-cache 友好之间取得平衡。
- 增加 React Dashboard，用于运行状态查看、Skill/Style 上传、MCP Server 管理和用户可配置 LLM API/base URL。

## 说明

本地开发不需要 Nginx。只有在需要 HTTPS、静态文件托管或反向代理规则时，才建议在部署环境中引入 Nginx。

</details>
