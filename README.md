# asakud-agent

<p align="center">
  <strong>A local long-running Agent with memory, tools, executable skills, style rewriting, MCP integration, and a React dashboard.</strong>
</p>

<h2 align="center">
  <a href="#english"><kbd>English</kbd></a>
  &nbsp;&nbsp;
  <a href="#中文"><kbd>中文</kbd></a>
</h2>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agent%20Workflow-1D4ED8?style=flat-square" />
  <img alt="React" src="https://img.shields.io/badge/React-Dashboard-61DAFB?style=flat-square&logo=react&logoColor=111111" />
  <img alt="Redis" src="https://img.shields.io/badge/Redis-Hot%20Memory-DC382D?style=flat-square&logo=redis&logoColor=white" />
</p>

<a id="english"></a>

## Overview

`asakud-agent` is a local, persistent Agent system designed for long-running personal assistant scenarios. It combines a LangGraph main workflow, asynchronous sub-agents, durable memory, browser-based web research, executable Skill packages, final-response Style rewriting, MCP tool integration, and a React dashboard.

Unlike a single-turn chatbot, this project keeps raw conversation history, compacts recent context, stages memory updates through Redis, writes stable knowledge into Markdown memory files, and lets the Agent grow reusable Skills from completed tasks.

## Highlights

- **Long-running Agent workflow**: LangGraph orchestrates message import, meme recognition, memory loading, LLM reasoning, tool calls, style rewriting, memory updates, Skill generation, and final output.
- **KV-cache-friendly memory design**: cold Markdown memory, Redis hot memory, and `RECENT_SUMMARY` are loaded in a stable prompt order to reduce unnecessary prompt churn.
- **Browser-capable web research**: `fetch_web` uses Playwright to search, browse, click, inspect accessibility snapshots, extract content, and summarize information in an isolated sub-workflow.
- **Executable Skill system**: Skill packages contain `SKILL.md`, references, optional Python scripts, and an entry definition. SkillRunner reads instructions with an LLM before deciding whether to run the script.
- **Async Skill builder**: high-value completed tasks can be converted into reusable Skill packages by a background `skill_builder` sub-agent.
- **Style packages**: final answers can be rewritten by an independent StyleRunner. ATRI is stored as a Style package rather than a task Skill.
- **MCP support**: MCP servers can be configured from the dashboard and exposed as runtime tools.
- **React dashboard**: monitor Agent/computer status, upload Skills and Styles, configure MCP servers, and edit model API settings.

## Architecture

```text
User / NapCat / Dashboard
        |
        v
FastAPI runtime
        |
        v
LangGraph main workflow
        |
        |-- import_db
        |-- router_meme
        |-- md_memory
        |-- agent_model
        |-- tools / run_skill loop
        |-- style
        |-- save_long_term
        |-- export_db
        |-- save_skill
        `-- print_meme
        |
        v
Final response
```

Prompt assembly order:

```text
B1: static system prompt + cold Markdown memory
B2: Redis hot memory
A: RECENT_SUMMARY
C: current user question
```

Sub-agent boundaries:

```text
fetch_web       -> search / browse / extract / summarize webpages
memory_worker   -> asynchronously merge hot memory into cold Markdown memory
skill_builder   -> asynchronously generate reusable Skill packages
skill_runner    -> read SKILL.md, references, and optionally run scripts
style_runner    -> rewrite final output into the selected speaking style
```

## Tech Stack

| Area | Technology |
| --- | --- |
| Agent orchestration | LangGraph, LangChain |
| Backend runtime | FastAPI, Uvicorn, Pydantic |
| Models | OpenAI-compatible LLM factory with main, route, and multimodal roles |
| Memory | SQLite, Redis, Markdown memory files |
| Web research | Playwright |
| Tooling | local tools, MCP server tools |
| Frontend | React, Vite |
| Messaging | NapCat-compatible callback and send APIs |

## Quick Start

### 1. Install backend dependencies

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment variables

```powershell
$env:MIMO_API_KEY="your_api_key"
```

The default model settings are stored in `agent.config.md`.

### 3. Bootstrap local files and database

```powershell
python agent_loop\bootstrap.py
```

### 4. Start the backend

```powershell
python main.py
```

The backend runs at:

```text
http://127.0.0.1:8000
```

### 5. Start the dashboard

```powershell
cd frontend
npm install
npm run dev
```

The dashboard runs at:

```text
http://127.0.0.1:5173
```

If your backend is not running on `127.0.0.1:8000`, set `VITE_API_BASE` before starting the frontend.

## Configuration

Runtime configuration lives in the fenced JSON block inside `agent.config.md`.

The LLM factory only keeps three model roles:

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

You can also update model `base_url`, `api_key`, model name, temperature, and output token limits from the dashboard settings page.

## Memory System

`asakud-agent` separates memory into stable cold memory, short prompt-facing summaries, and hot pending updates.

| Layer | Storage | Purpose |
| --- | --- | --- |
| Raw history | SQLite | append-only user/assistant conversation records |
| Recent summary | `memory/RECENT_SUMMARY.md` | compacted context loaded into the current prompt |
| Cold memory | Markdown files | stable facts, self-knowledge, pending facts, and archived core memory |
| Hot memory | Redis | temporary pending updates before asynchronous Markdown writes |

Markdown memory files:

```text
memory/
|-- MEMORY.md
|-- SELF.md
|-- CORE.md
|-- PENDING.md
`-- RECENT_SUMMARY.md
```

## Skills

Skills are reusable executable task packages.

```text
skills/
|-- skill.config.md
|-- _templates/
|-- generated/
`-- imported-skill/
    |-- SKILL.md
    |-- skill.json
    |-- reference/
    `-- scripts/
```

Execution model:

```text
Main Agent
  -> decides whether to call run_skill
SkillRunnerAgent
  -> reads SKILL.md and references with an LLM
  -> exposes run_skill_script only when the Skill has an executable entry
  -> script owns fetch_web / MCP calls through context["run_tool"]
  -> returns a task result to the main workflow
StyleRunner
  -> rewrites the final user-facing answer
```

This design keeps Skill execution explainable: the sub-agent reads the Skill package first, while deterministic actions remain inside the script.

## Styles

Styles are final-response rewrite packages. They are separate from executable Skills.

```text
styles/
|-- style.config.md
`-- atri/
    |-- SKILL.md
    |-- soul.md
    |-- limit.md
    `-- resource/
```

ATRI is the default Style. The main workflow produces the factual/task result first, then StyleRunner rewrites it into the selected tone.

## MCP Tools

MCP is disabled by default. You can add a real MCP server from the dashboard.

Supported modes:

- `mcp-jsonrpc`: MCP JSON-RPC / Streamable HTTP endpoint, commonly ending in `/mcp`.
- `simple-http`: REST-like gateway using `/tools` and `/tools/call`.

Remote tools are exposed with names such as:

```text
mcp.my-server.search
mcp.my-server.fetch
```

## Dashboard API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/dashboard/status` | Agent, computer, and runtime status |
| `GET` | `/api/dashboard/models` | Read model configuration |
| `PUT` | `/api/dashboard/models` | Update model API settings |
| `GET` | `/api/dashboard/skills` | List registered Skills |
| `POST` | `/api/dashboard/skills/upload` | Upload a Skill zip package |
| `GET` | `/api/dashboard/styles` | List response Styles |
| `POST` | `/api/dashboard/styles/upload` | Upload a Style zip package |
| `GET` | `/api/dashboard/mcp` | List MCP servers |
| `POST` | `/api/dashboard/mcp/servers` | Add or update an MCP server |
| `GET` | `/api/dashboard/mcp/servers/{server_name}/tools` | Probe MCP tools |

## Project Structure

```text
asakud-agent/
|-- main.py
|-- agent.config.md
|-- llm/
|-- agent_loop/
|-- compact/
|-- db/
|-- frontend/
|-- memory/
|-- memory_worker/
|-- prompts/
|-- skills/
|-- skill_builder/
|-- skill_runner/
|-- styles/
|-- style_runner/
|-- tools/
`-- meme/
```

## Resume Highlights

- Built a LangGraph-based local long-running Agent with memory, tool use, executable Skills, Style finalization, and async sub-agents.
- Implemented a Playwright-based `fetch_web` sub-workflow that isolates search, browsing, extraction, and summarization from the main workflow to reduce context interference and token overhead.
- Designed an executable Skill system where the main Agent routes tasks, SkillRunner reads `SKILL.md` and references, and scripts own `fetch_web/MCP` calls through a controlled runtime context.
- Added an async `skill_builder` sub-agent with local templates to generate reusable Skill packages containing instructions, references, and optional executable scripts.
- Implemented Redis hot memory, Markdown cold memory, and RECENT_SUMMARY compaction to balance personalization, persistence, and KV-cache friendliness.
- Built a React dashboard for runtime status, Skill/Style uploads, MCP server management, and user-configurable LLM API settings.

## Roadmap

- Add stricter sandboxing for user-uploaded Skill scripts.
- Add MCP connection health checks and per-server tool permissions.
- Add dashboard views for memory events and Skill execution traces.
- Add automated tests for workflow routing, memory compaction, and Skill execution.
- Add Docker Compose for backend, frontend, Redis, and optional MCP gateway.

## Notes

Nginx is not required for local development. Use it only when deploying behind HTTPS, static-file serving, or reverse proxy rules.

<p align="right">
  <a href="#asakud-agent">Back to top</a>
</p>

---

<a id="中文"></a>

# asakud-agent 中文版

<p align="center">
  <strong>一个本地长期运行的 Agent 系统，集成记忆、工具、可执行 Skill、Style 改写、MCP 和 React 控制台。</strong>
</p>

<h2 align="center">
  <a href="#english"><kbd>English</kbd></a>
  &nbsp;&nbsp;
  <a href="#中文"><kbd>中文</kbd></a>
</h2>

## 项目简介

`asakud-agent` 是一个面向本地长期运行场景的智能体系统。它以 LangGraph 主工作流为核心，结合异步子 Agent、长期记忆、浏览器网页检索、可执行 Skill、最终回复 Style 改写、MCP 工具接入和 React Dashboard。

它不是一次性聊天脚本，而是一个可持续运行的个人 Agent 服务：原始对话写入 SQLite，近期上下文压缩为 `RECENT_SUMMARY`，待写入记忆先进入 Redis 热记忆，稳定知识再异步合并进 Markdown 冷记忆，同时还能从高价值任务中沉淀可复用 Skill。

## 核心亮点

- **长期运行 Agent 工作流**：LangGraph 编排消息导入、表情识别、记忆加载、LLM 推理、工具调用、Style 改写、记忆更新、Skill 生成和最终输出。
- **KV-cache 友好的记忆设计**：冷 Markdown 记忆、Redis 热记忆和 `RECENT_SUMMARY` 按稳定顺序加载，减少不必要的 prompt 抖动。
- **具备浏览器能力的网页检索**：`fetch_web` 使用 Playwright 完成搜索、浏览、点击、可访问性快照、内容提取和总结，并隔离在子工作流中执行。
- **可执行 Skill 系统**：Skill 包包含 `SKILL.md`、references、可选 Python 脚本和入口定义，SkillRunner 会先用 LLM 阅读说明，再判断是否运行脚本。
- **异步 Skill 构建**：高价值已完成任务可以由后台 `skill_builder` 子 Agent 转换成可复用 Skill 包。
- **Style 包机制**：最终回复由独立 StyleRunner 改写，ATRI 被保存为 Style 包，而不是任务 Skill。
- **MCP 支持**：可以从 Dashboard 添加 MCP Server，并动态暴露为运行时工具。
- **React Dashboard**：支持查看 Agent/电脑状态、上传 Skill/Style、配置 MCP Server 和修改模型 API 设置。

## 架构

```text
用户 / NapCat / Dashboard
        |
        v
FastAPI 运行时
        |
        v
LangGraph 主工作流
        |
        |-- import_db
        |-- router_meme
        |-- md_memory
        |-- agent_model
        |-- tools / run_skill loop
        |-- style
        |-- save_long_term
        |-- export_db
        |-- save_skill
        `-- print_meme
        |
        v
最终回复
```

Prompt 组装顺序：

```text
B1: 静态 system prompt + 冷 Markdown 记忆
B2: Redis 热记忆
A: RECENT_SUMMARY
C: 当前用户问题
```

子 Agent 边界：

```text
fetch_web       -> 搜索 / 浏览 / 提取 / 总结网页
memory_worker   -> 异步将热记忆合并进冷 Markdown 记忆
skill_builder   -> 异步生成可复用 Skill 包
skill_runner    -> 阅读 SKILL.md、references，并可选择运行脚本
style_runner    -> 将最终输出改写成指定语气
```

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Agent 编排 | LangGraph, LangChain |
| 后端运行时 | FastAPI, Uvicorn, Pydantic |
| 模型层 | OpenAI-compatible LLM factory，分为主模型、路由模型、多模态模型 |
| 记忆系统 | SQLite, Redis, Markdown |
| 网页检索 | Playwright |
| 工具系统 | 本地工具, MCP Server 工具 |
| 前端 | React, Vite |
| 消息接入 | NapCat callback/send API |

## 快速开始

### 1. 安装后端依赖

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

```powershell
$env:MIMO_API_KEY="your_api_key"
```

默认模型配置位于 `agent.config.md`。

### 3. 初始化本地文件和数据库

```powershell
python agent_loop\bootstrap.py
```

### 4. 启动后端

```powershell
python main.py
```

后端默认运行在：

```text
http://127.0.0.1:8000
```

### 5. 启动前端 Dashboard

```powershell
cd frontend
npm install
npm run dev
```

前端默认运行在：

```text
http://127.0.0.1:5173
```

如果后端不在 `127.0.0.1:8000`，启动前端前请设置 `VITE_API_BASE`。

## 配置说明

运行时配置位于 `agent.config.md` 的 fenced JSON 代码块中。

LLM 工厂只保留三个模型角色：

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

你也可以在 Dashboard 设置页修改模型 `base_url`、`api_key`、模型名、温度和输出 token 限制。

## 记忆系统

`asakud-agent` 将记忆分为稳定冷记忆、近期摘要和热更新队列。

| 层级 | 存储 | 用途 |
| --- | --- | --- |
| 原始历史 | SQLite | 追加保存 user/assistant 完整对话 |
| 近期摘要 | `memory/RECENT_SUMMARY.md` | 压缩后的 prompt 可见上下文 |
| 冷记忆 | Markdown 文件 | 稳定事实、自我认知、待确认事实、归档核心记忆 |
| 热记忆 | Redis | 异步写入 Markdown 前的临时更新 |

Markdown 记忆文件：

```text
memory/
|-- MEMORY.md
|-- SELF.md
|-- CORE.md
|-- PENDING.md
`-- RECENT_SUMMARY.md
```

## Skill 系统

Skill 是可复用的可执行任务包。

```text
skills/
|-- skill.config.md
|-- _templates/
|-- generated/
`-- imported-skill/
    |-- SKILL.md
    |-- skill.json
    |-- reference/
    `-- scripts/
```

执行模型：

```text
Main Agent
  -> 判断是否调用 run_skill
SkillRunnerAgent
  -> 使用 LLM 阅读 SKILL.md 和 references
  -> 只有当 Skill 存在可执行 entry 时才暴露 run_skill_script
  -> 脚本通过 context["run_tool"] 自己调用 fetch_web / MCP
  -> 将任务结果返回主流程
StyleRunner
  -> 统一改写最终面向用户的回答
```

这个设计让 Skill 执行更清晰：子 Agent 先阅读 Skill 包，确定性动作则留在脚本内部。

## Style 系统

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

ATRI 是默认 Style。主工作流先产出事实性任务结果，再由 StyleRunner 改写成指定语气。

## MCP 工具

MCP 默认关闭，可以从 Dashboard 添加真实 MCP Server。

支持模式：

- `mcp-jsonrpc`：MCP JSON-RPC / Streamable HTTP 端点，通常以 `/mcp` 结尾。
- `simple-http`：REST 风格网关，使用 `/tools` 和 `/tools/call`。

远程工具会以类似下面的名字暴露：

```text
mcp.my-server.search
mcp.my-server.fetch
```

## Dashboard API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/dashboard/status` | Agent、电脑和运行时状态 |
| `GET` | `/api/dashboard/models` | 读取模型配置 |
| `PUT` | `/api/dashboard/models` | 更新模型 API 设置 |
| `GET` | `/api/dashboard/skills` | 列出已注册 Skill |
| `POST` | `/api/dashboard/skills/upload` | 上传 Skill zip 包 |
| `GET` | `/api/dashboard/styles` | 列出 Style |
| `POST` | `/api/dashboard/styles/upload` | 上传 Style zip 包 |
| `GET` | `/api/dashboard/mcp` | 列出 MCP Server |
| `POST` | `/api/dashboard/mcp/servers` | 添加或更新 MCP Server |
| `GET` | `/api/dashboard/mcp/servers/{server_name}/tools` | 探测 MCP 工具 |

## 项目结构

```text
asakud-agent/
|-- main.py
|-- agent.config.md
|-- llm/
|-- agent_loop/
|-- compact/
|-- db/
|-- frontend/
|-- memory/
|-- memory_worker/
|-- prompts/
|-- skills/
|-- skill_builder/
|-- skill_runner/
|-- styles/
|-- style_runner/
|-- tools/
`-- meme/
```

## 简历亮点

- 构建基于 LangGraph 的本地长期运行 Agent，集成记忆、工具调用、可执行 Skill、Style 终稿改写和异步子 Agent。
- 实现基于 Playwright 的 `fetch_web` 子工作流，将搜索、浏览、提取和总结从主流程隔离，减少上下文干扰和 token 消耗。
- 设计可执行 Skill 系统：主 Agent 负责任务路由，SkillRunner 阅读 `SKILL.md` 和 references，脚本通过受控 runtime context 调用 `fetch_web/MCP`。
- 实现异步 `skill_builder` 子 Agent，结合本地模板生成包含说明、references 和可选脚本的可复用 Skill 包。
- 实现 Redis 热记忆、Markdown 冷记忆和 RECENT_SUMMARY 压缩，在个性化、持久化和 KV-cache 友好之间取得平衡。
- 构建 React Dashboard，支持运行状态查看、Skill/Style 上传、MCP Server 管理和用户可配置 LLM API。

## 后续规划

- 为用户上传的 Skill 脚本增加更严格的沙箱。
- 增加 MCP 连接健康检查和按 Server 的工具权限控制。
- 增加 Dashboard 中的记忆事件和 Skill 执行轨迹视图。
- 增加工作流路由、记忆压缩和 Skill 执行的自动化测试。
- 增加 Docker Compose，一键启动后端、前端、Redis 和可选 MCP 网关。

## 说明

本地开发不需要 Nginx。只有在需要 HTTPS、静态文件托管或反向代理规则时，才建议在部署环境中引入 Nginx。

<p align="right">
  <a href="#asakud-agent">返回顶部</a>
</p>
