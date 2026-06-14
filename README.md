# asakud-agent

`asakud-agent` is a local long-running agent system built with LangGraph, LangChain, FastAPI, SQLite, Markdown memory, and extensible tools.

`asakud-agent` 是一个基于 LangGraph、LangChain、FastAPI、SQLite、Markdown Memory 和可扩展工具体系构建的本地长运行 Agent 项目。

## Overview

This project is designed as a persistent assistant service rather than a one-shot script. It can receive external messages, keep short-term and long-term memory, execute scheduled tasks, call tools, and delegate focused work such as web research to child workflows.

这个项目的目标不是一次性脚本，而是一个可持续运行的智能助理服务。它能够接收外部消息、维护短期和长期记忆、执行定时任务、调用工具，并将网页检索等专项任务下放给子工作流处理。

## Features

- Workflow-first architecture powered by LangGraph.
- Hybrid memory design with SQLite session state and Markdown long-term memory.
- FastAPI service runtime for continuous operation.
- NapCat integration for message receiving and sending.
- Tool registry that supports built-in tools, browser-based tools, and MCP tools.
- Child workflow support, including a Playwright-powered `fetch_web` sub-agent.
- Meme collection, emotion tagging, and meme selection flow.

- 基于 LangGraph 的工作流式 Agent 架构。
- SQLite 会话状态 + Markdown 长期记忆的混合记忆设计。
- 基于 FastAPI 的常驻服务运行方式。
- 集成 NapCat，支持消息接收与发送。
- 统一工具注册机制，支持内置工具、浏览器工具和 MCP 工具。
- 支持子工作流，例如基于 Playwright 的 `fetch_web` 检索子 Agent。
- 支持表情包收集、情绪标注与发送选择流程。

## Architecture

```text
Incoming message
  -> router / skill loader / memory loader
  -> RAG / Markdown memory retrieval
  -> main model
  -> tool execution if needed
  -> long-term memory write-back
  -> short-term memory trimming
  -> final response / meme output
```

Core modules:

- `main.py`: FastAPI entrypoint and NapCat bridge.
- `agent_loop/workflow.py`: main LangGraph workflow definition.
- `agent_loop/nodes/`: router, memory, RAG, skill, meme, and output nodes.
- `db/runtime/`: SQLite-backed runtime state.
- `memory/`: Markdown memory files and write-back logic.
- `tools/`: tool registry, local tools, and child workflows such as `fetch_web`.

核心模块：

- `main.py`：FastAPI 服务入口与 NapCat 消息桥接层。
- `agent_loop/workflow.py`：主 LangGraph 工作流定义。
- `agent_loop/nodes/`：路由、记忆、RAG、技能、表情包和输出节点。
- `db/runtime/`：基于 SQLite 的运行时状态存储。
- `memory/`：Markdown 记忆文件与写回逻辑。
- `tools/`：工具注册中心、本地工具以及 `fetch_web` 等子工作流。

## Project Structure

```text
asakud-agent/
├─ agent.config.md
├─ main.py
├─ agent_loop/
│  ├─ workflow.py
│  ├─ models/
│  └─ nodes/
├─ db/
├─ memory/
├─ tools/
│  ├─ registry.py
│  └─ fetch_web/
├─ skills/
└─ meme/
```

## Quick Start

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

If you want the `fetch_web` child workflow to control a real browser:

```powershell
pip install playwright
playwright install chromium
```

如果你希望 `fetch_web` 子工作流真正驱动浏览器，还需要额外安装 Playwright：

```powershell
pip install playwright
playwright install chromium
```

### 2. Bootstrap runtime files

```powershell
python agent_loop\bootstrap.py
```

This step prepares configured runtime resources such as:

- Markdown memory files
- SQLite schema and database
- skill registry files
- meme storage directories

这一步会生成和初始化运行时资源，例如：

- Markdown 记忆文件
- SQLite 数据库与 schema
- skill registry 文件
- meme 存储目录

### 3. Start the service

```powershell
python main.py
```

## Configuration

All runtime configuration is stored in the fenced JSON block inside `agent.config.md`.

Important sections:

- `model`: main chat model
- `route_model`: lightweight routing / utility model
- `multimodal_model`: image-capable model for meme analysis
- `memory`: Markdown memory definitions and SQLite setup
- `db`: session database paths and defaults
- `loop`: workflow loop settings
- `tools`: enabled tools
- `napcat`: message bridge settings
- `meme`: meme storage and send/collect behavior

所有运行配置都放在 `agent.config.md` 的 JSON 代码块中。

重点配置项包括：

- `model`：主对话模型
- `route_model`：轻量路由/工具模型
- `multimodal_model`：用于表情识别的多模态模型
- `memory`：Markdown 记忆和 SQLite 配置
- `db`：会话数据库路径与默认设置
- `loop`：工作流循环参数
- `tools`：启用的工具列表
- `napcat`：消息桥接配置
- `meme`：表情包存储与收发行为配置

## Tooling

The tool system is registry-based.

- Built-in tools are defined in `tools/registry.py`.
- Browser-oriented web tools live in `tools/fetch_web/tools.py`.
- The `fetch_web` child workflow lives in `tools/fetch_web/client.py`.
- MCP tools can be loaded dynamically through configuration.

工具系统基于统一注册中心。

- 内置工具定义在 `tools/registry.py`
- 面向浏览器交互的网页工具定义在 `tools/fetch_web/tools.py`
- `fetch_web` 子工作流定义在 `tools/fetch_web/client.py`
- MCP 工具可以通过配置动态接入

## Workflow Notes

### Main workflow

The main workflow handles memory loading, routing, model execution, tool invocation, memory write-back, and final output formatting.

主工作流负责记忆加载、路由决策、模型执行、工具调用、记忆写回以及最终输出整理。

### `fetch_web` child workflow

The `fetch_web` workflow is a focused web-research sub-agent. It uses a smaller context than the main workflow, which helps reduce irrelevant prompt overhead during browser-based retrieval tasks.

`fetch_web` 是一个专门负责网页检索的子 Agent。它使用比主工作流更轻的上下文，能减少浏览器检索场景中的无关提示词负担。

Typical flow:

1. Search or open a target page.
2. Inspect the page state.
3. Click into relevant results.
4. Extract target information.
5. Return a concise answer to the parent agent.

典型流程：

1. 搜索或打开目标页面。
2. 检查当前页面状态。
3. 点击相关结果继续深入。
4. 抽取目标信息。
5. 向父 Agent 返回精简结论。

## API / Entry Points

- `POST /getMessage`: receive NapCat callback messages
- `POST /sendMessage`: send outbound messages through NapCat
- `agent_loop/loop.py`: run the main workflow once from Python or CLI

## Use Cases

- Personal local assistant with persistent memory
- QQ/NapCat-connected chat agent
- Tool-augmented workflow experiments
- Browser-based web retrieval through a child agent
- Local meme collection and contextual meme reply experiments

- 带长期记忆的本地个人助理
- 接入 QQ / NapCat 的聊天 Agent
- 工具增强型工作流实验项目
- 通过子 Agent 实现浏览器检索
- 本地表情包收集与上下文发图实验

## Highlights

- Explicit workflow modeling instead of hidden orchestration.
- Memory separation between short-term state and durable knowledge.
- Tool modularity across local tools, browser tools, and remote MCP tools.
- Practical sub-agent design for high-noise tasks such as web browsing.

- 显式工作流建模，而不是隐式流程拼接。
- 短期状态与长期知识分层管理。
- 本地工具、浏览器工具和 MCP 工具共用统一执行路径。
- 对网页检索这类高噪声任务采用子 Agent 拆分设计。

## Development Notes

- Re-run `python agent_loop\bootstrap.py` after changing config-backed runtime resources.
- Install Playwright only if you need real browser automation.
- Group-chat message handling currently requires explicit `@agent` mentions before the workflow runs.

- 如果修改了受配置驱动的运行时资源，请重新执行 `python agent_loop\bootstrap.py`
- 只有在需要真实浏览器控制时才安装 Playwright
- 当前群聊消息需要显式 `@agent` 才会进入工作流
