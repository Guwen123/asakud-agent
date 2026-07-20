# asakud-agent

<p align="center">
  <strong>A Web Research Agent for searching, browsing, extracting, and summarizing public web information.</strong>
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
  <img alt="Playwright" src="https://img.shields.io/badge/Playwright-Web%20Research-2EAD33?style=flat-square&logo=playwright&logoColor=white" />
  <img alt="React" src="https://img.shields.io/badge/React-Dashboard-61DAFB?style=flat-square&logo=react&logoColor=111111" />
</p>

<a id="english"></a>

## Overview

`asakud-agent` is a local Web Research Agent designed for open-web information collection and synthesis. It uses a LangGraph main workflow to coordinate model reasoning, tool calls, executable Skills, browser-based search, page interaction, information extraction, source summarization, and final response rewriting.

The project is positioned around practical research tasks such as job-market scanning, company/news monitoring, stock or finance information lookup, GitHub/project research, and multi-page topic summaries. Instead of behaving like a single API wrapper, it decomposes web research into specialized sub-workflows and makes the whole process observable from a React dashboard.

## Key Features

- **Web research workflow**: orchestrates search planning, browser navigation, page interaction, content extraction, evidence aggregation, and final summarization.
- **Isolated `fetch_web` sub-agent**: keeps noisy browser snapshots and page content out of the main workflow context, reducing irrelevant prompt interference and token pressure.
- **Playwright browser tools**: supports opening pages, clicking elements, collecting accessibility-tree snapshots, extracting page text, and returning structured page state to the LLM.
- **Executable Skill system**: turns repeatable research tasks, such as job search or stock lookup, into reusable Skill packages with `SKILL.md`, references, optional scripts, and entry metadata.
- **Asynchronous Skill builder**: can promote valuable completed tasks into reusable Skills in the background.
- **Memory for research preferences**: stores user preferences such as target roles, cities, industries, tracked tickers, preferred sources, and output style without making memory the main product focus.
- **MCP integration**: allows additional remote tools to be loaded from configurable MCP servers.
- **Persistent crawl records**: stores each `fetch_web` query, crawl date, status, and result in SQLite and exposes them in the dashboard.
- **Observability dashboard**: visualizes runtime status, node duration, tool latency, token usage, Skill/Style configuration, MCP servers, NapCat connection, and model settings.

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
        |     |-- fetch_web sub-agent
        |     |-- SkillRunnerAgent
        |     `-- MCP tools
        |-- style
        |-- save_long_term
        |-- export_db
        |-- save_skill
        `-- print_meme
        |
        v
Final researched answer
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
fetch_web       -> search / browse / click / extract / summarize webpages
skill_runner    -> read SKILL.md, references, and optionally run scripts
skill_builder   -> asynchronously generate reusable research Skill packages
memory_worker   -> asynchronously merge hot memory into cold Markdown memory
style_runner    -> rewrite final output into the selected speaking style
reminder_worker -> poll structured reminder rows and dispatch due NapCat messages
```

## Typical Use Cases

- Search job platforms and summarize matching internships or full-time positions.
- Track public information about companies, products, competitors, or GitHub projects.
- Search multiple pages for a topic and return a structured summary.
- Query public stock/finance pages and summarize price movement or related news.
- Convert frequent research workflows into reusable executable Skills.

## Tech Stack

| Area | Technology |
| --- | --- |
| Agent orchestration | LangGraph, LangChain |
| Backend runtime | FastAPI, Uvicorn, Pydantic |
| Browser automation | Playwright |
| Models | OpenAI-compatible LLM factory with main, route, and multimodal roles |
| Memory | SQLite, Redis, Markdown memory files |
| Skills | `SKILL.md`, references, optional Python scripts, SkillRunnerAgent |
| Tool extension | Built-in tools, MCP server tools |
| Observability | Runtime performance traces, LangSmith-ready evaluation scripts |
| Frontend | React, Vite |
| Messaging | NapCat-compatible callback and send APIs |

## Quick Start

### 1. Install backend dependencies

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. Start the backend

```powershell
python main.py
```

`main.py` automatically runs bootstrap during FastAPI startup, so `python agent_loop\bootstrap.py` is not required for normal startup.

The backend runs at:

```text
http://127.0.0.1:8000
```

### 3. Start the dashboard

```powershell
cd frontend
npm install
npm run dev
```

The dashboard runs at:

```text
http://127.0.0.1:5173
```

### 4. Configure models

Open the dashboard Settings page, enter `base_url` and `api_key`, click **Get Models**, and select model names for:

- `main_model`
- `route_model`
- `multimodal_model`

The dashboard writes model settings into `agent.config.md`.

## Web Research Tools

The core web capability lives in `tools/fetch_web/`.

```text
tools/fetch_web/
|-- client.py      # LangGraph sub-workflow
|-- fetch.py       # main fetch_web tool exposed to the Agent
`-- tools.py       # Playwright browser tools
```

The child workflow is constrained to:

```text
search -> open result -> inspect page -> extract evidence -> summarize
```

This keeps browser context isolated from the main Agent and makes web research tasks more stable.

## Skills

Skills are reusable executable research packages.

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
  -> decides whether a task should call run_skill
SkillRunnerAgent
  -> reads SKILL.md and references
  -> exposes run_skill_script only when the Skill has an executable entry
  -> returns structured task output to the main workflow
StyleRunner
  -> rewrites the final user-facing answer
```

Skill scripts can call project tools through the injected execution context when the Skill declares allowed tools.

## Memory

Memory is used to improve research continuity, not to define the product identity. It can store stable user preferences such as:

- preferred job locations and roles
- tracked stocks or companies
- preferred sources and output formats
- recurring research interests

Storage layers:

| Layer | Storage | Purpose |
| --- | --- | --- |
| Raw history | SQLite | append-only user/assistant conversation records |
| Recent summary | `memory/RECENT_SUMMARY.md` | compacted context loaded into the current prompt |
| Cold memory | Markdown files | stable facts, preferences, pending facts, and archived memory |
| Hot memory | Redis | temporary pending updates before asynchronous Markdown writes |

## Observability and Evaluation

The dashboard and test suite focus on Agent engineering quality:

- node execution duration
- tool call latency
- model token usage
- Skill execution traces
- static configuration checks
- LangSmith-ready evaluation entry points under `test/`

Run tests:

```powershell
python -m unittest discover -s test -p "test_*.py"
```

Build frontend:

```powershell
cd frontend
npm run build
```

## Project Structure

```text
asakud-agent/
|-- main.py
|-- agent.config.md
|-- agent_loop/
|-- compact/
|-- db/
|-- frontend/
|-- llm/
|-- memory/
|-- memory_worker/
|-- prompts/
|-- skills/
|-- skill_builder/
|-- skill_runner/
|-- styles/
|-- style_runner/
|-- test/
`-- tools/
```

<p align="right">
  <a href="#asakud-agent">Back to top</a>
</p>

---

<a id="中文"></a>

# asakud-agent 中文版

<p align="center">
  <strong>面向公开网页信息检索、浏览、提取与汇总的 Web Research Agent。</strong>
</p>

<h2 align="center">
  <a href="#english"><kbd>English</kbd></a>
  &nbsp;&nbsp;
  <a href="#中文"><kbd>中文</kbd></a>
</h2>

## 项目简介

`asakud-agent` 是一个本地运行的 Web Research Agent，面向公开网页信息获取与汇总场景。项目基于 LangGraph 编排主工作流，结合浏览器自动化、工具调用、可执行 Skill、网页信息提取、多源摘要、最终回复风格改写和 React Dashboard。

它的核心目标不是做普通聊天机器人，而是解决真实的信息检索问题：招聘信息分散、网页结构不稳定、人工搜索成本高、信息来源难追踪、重复任务难复用。Agent 会将复杂网页任务拆成搜索、浏览、点击、提取、汇总等步骤，并通过子工作流降低主流程上下文干扰和 Token 压力。

## 核心能力

- **网页研究工作流**：支持搜索规划、浏览器访问、页面交互、内容提取、证据聚合和最终总结。
- **`fetch_web` 子 Agent**：将网页快照、页面正文和交互元素隔离在子上下文中，减少主 Agent 的无关提示信息和 Token 消耗。
- **Playwright 浏览器工具**：支持打开网页、点击元素、获取 accessibility tree、提取页面正文和返回结构化页面状态。
- **可执行 Skill 系统**：可将 Boss 招聘检索、股票信息查询、项目调研等高频网页任务沉淀为可复用 Skill。
- **异步 Skill Builder**：将高价值已完成任务后台转化为 Skill 包，提升复杂任务复用能力。
- **研究偏好记忆**：记录用户关注的城市、岗位、行业、公司、股票代码、常用信息源和输出格式。
- **MCP 扩展**：支持从 Dashboard 配置 MCP Server，并将远程工具暴露给 Agent。
- **爬取记录持久化**：将每次 `fetch_web` 的查询、爬取日期、状态和结果写入 SQLite，并在 Dashboard 中展示。
- **可观测 Dashboard**：展示节点耗时、工具延迟、Token 消耗、Skill/Style 状态、MCP Server、NapCat 和模型配置。

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
        |     |-- fetch_web 子 Agent
        |     |-- SkillRunnerAgent
        |     `-- MCP tools
        |-- style
        |-- save_long_term
        |-- export_db
        |-- save_skill
        `-- print_meme
        |
        v
最终研究结果
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
fetch_web       -> 搜索 / 浏览 / 点击 / 提取 / 总结网页
skill_runner    -> 阅读 SKILL.md、references，并可选运行脚本
skill_builder   -> 异步生成可复用研究 Skill 包
memory_worker   -> 异步将热记忆合并进冷 Markdown 记忆
style_runner    -> 将最终输出改写为指定语气
reminder_worker -> 轮询结构化提醒并通过 NapCat 发送到期消息
```

## 典型场景

- 搜索招聘网站并汇总匹配的实习或全职岗位。
- 跟踪公司、产品、竞品、新闻或 GitHub 项目的公开信息。
- 对一个主题检索多个网页并输出结构化摘要。
- 查询公开股票/财经页面并总结涨跌、公告或相关新闻。
- 将高频网页研究流程沉淀为可复用 Skill。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Agent 编排 | LangGraph, LangChain |
| 后端运行时 | FastAPI, Uvicorn, Pydantic |
| 浏览器自动化 | Playwright |
| 模型层 | OpenAI-compatible LLM factory，包含主模型、路由模型、多模态模型 |
| 记忆系统 | SQLite, Redis, Markdown |
| Skill 系统 | `SKILL.md`, references, Python scripts, SkillRunnerAgent |
| 工具扩展 | 内置工具, MCP Server 工具 |
| 可观测性 | 节点耗时、工具延迟、Token 消耗、LangSmith-ready 评估脚本 |
| 前端 | React, Vite |
| 消息接入 | NapCat callback/send API |

## 快速开始

### 1. 安装后端依赖

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动后端

```powershell
python main.py
```

`main.py` 会在 FastAPI 启动时自动执行 bootstrap，正常启动不需要手动运行 `python agent_loop\bootstrap.py`。

默认后端地址：

```text
http://127.0.0.1:8000
```

### 3. 启动前端 Dashboard

```powershell
cd frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

### 4. 配置模型

打开 Dashboard 的 Settings 页面，填写 `base_url` 和 `api_key`，点击 **Get Models / 获取模型**，然后为以下角色选择模型：

- `main_model`
- `route_model`
- `multimodal_model`

Dashboard 会将模型配置写入 `agent.config.md`。

## 网页研究工具

核心网页能力位于 `tools/fetch_web/`。

```text
tools/fetch_web/
|-- client.py      # LangGraph 子工作流
|-- fetch.py       # 暴露给主 Agent 的 fetch_web 工具
`-- tools.py       # Playwright 浏览器工具
```

子流程约束为：

```text
搜索 -> 打开结果 -> 检查页面 -> 提取证据 -> 总结
```

这样可以把浏览器上下文隔离在子 Agent 中，让主 Agent 更专注于任务决策和最终输出。

## Skill 系统

Skill 是可复用的网页研究任务包。

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
  -> 阅读 SKILL.md 和 references
  -> 只有当 Skill 存在可执行 entry 时才暴露 run_skill_script
  -> 将结构化任务结果返回给主流程
StyleRunner
  -> 统一改写最终面向用户的回答
```

当 Skill 声明允许工具时，脚本可以通过注入的执行上下文调用项目工具。

## 记忆系统

记忆用于增强研究连续性，而不是作为项目主定位。适合记录：

- 用户关注的岗位、城市、行业
- 长期跟踪的股票、公司或产品
- 偏好的信息源和输出格式
- 重复出现的研究兴趣

| 层级 | 存储 | 用途 |
| --- | --- | --- |
| 原始历史 | SQLite | append-only 保存 user/assistant 对话 |
| 近期摘要 | `memory/RECENT_SUMMARY.md` | 压缩后的 prompt 可见上下文 |
| 冷记忆 | Markdown 文件 | 稳定事实、偏好、待确认事实和归档记忆 |
| 热记忆 | Redis | 写入 Markdown 前的临时更新 |

## 可观测与评估

项目内置 Dashboard 和测试体系，用于评估 Agent 工程质量：

- 节点执行时长
- 工具调用延迟
- 模型 Token 消耗
- Skill 执行轨迹
- 静态配置检查
- `test/` 下的 LangSmith-ready 评估入口

运行测试：

```powershell
python -m unittest discover -s test -p "test_*.py"
```

构建前端：

```powershell
cd frontend
npm run build
```

## 项目结构

```text
asakud-agent/
|-- main.py
|-- agent.config.md
|-- agent_loop/
|-- compact/
|-- db/
|-- frontend/
|-- llm/
|-- memory/
|-- memory_worker/
|-- prompts/
|-- skills/
|-- skill_builder/
|-- skill_runner/
|-- styles/
|-- style_runner/
|-- test/
`-- tools/
```

<p align="right">
  <a href="#asakud-agent">返回顶部</a>
</p>
