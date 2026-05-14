from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent_loop.bootstrap import bootstrap
from agent_loop.config_loader import load_config, project_path
from agent_loop.loop import run_agent_once_async
from http_client import AsyncHttpClient
from memory.markdown import add_markdown_memory, list_markdown_memories
from memory.routing import route_storage_with_llm
from tools.registry import ToolRegistry


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    output: str


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = {}


class MemoryWriteRequest(BaseModel):
    memory_id: str
    content: str
    section: str | None = None
    reason: str | None = None
    source: str = "api"


class StorageRouteRequest(BaseModel):
    content: str
    context: str = ""


class HealthResponse(BaseModel):
    status: str
    agent: str
    database: str


def ensure_app_state(app: FastAPI) -> None:
    if not hasattr(app.state, "config"):
        bootstrap()
        app.state.config = load_config()
    if not hasattr(app.state, "tools"):
        app.state.tools = ToolRegistry(app.state.config.get("tools", {}).get("enabled"))
    if not hasattr(app.state, "http_client"):
        app.state.http_client = AsyncHttpClient()


async def scheduled_task_loop(app: FastAPI) -> None:
    while True:
        config = app.state.config
        interval = config.get("server", {}).get("scheduler_interval_seconds", 30)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    app.state.config = load_config()
    app.state.tools = ToolRegistry(app.state.config.get("tools", {}).get("enabled"))
    app.state.http_client = AsyncHttpClient()
    await app.state.http_client.start()
    app.state.scheduler_task = asyncio.create_task(scheduled_task_loop(app))
    try:
        yield
    finally:
        app.state.scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.scheduler_task
        await app.state.http_client.aclose()


app = FastAPI(
    title="Sakuro Agent",
    description="长期运行的本地 Agent 服务。",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ensure_app_state(app)
    config: dict[str, Any] = app.state.config
    return HealthResponse(
        status="ok",
        agent=config["agent"]["name"],
        database=str(project_path(config["paths"]["database"])),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    output = await run_agent_once_async(request.message)
    return ChatResponse(output=output)


@app.get("/tools")
async def list_tools() -> list[dict[str, str]]:
    ensure_app_state(app)
    return app.state.tools.describe()


@app.post("/tools/{tool_name}/run")
async def run_tool(tool_name: str, request: ToolRequest) -> dict[str, Any]:
    ensure_app_state(app)
    result = app.state.tools.run(tool_name, request.arguments)
    return {"tool": tool_name, "result": result}


@app.get("/memory/markdown")
async def list_memory_files() -> list[dict[str, object]]:
    ensure_app_state(app)
    return list_markdown_memories(app.state.config)


@app.post("/memory/markdown")
async def write_memory(request: MemoryWriteRequest) -> dict[str, str]:
    ensure_app_state(app)
    return add_markdown_memory(
        memory_id=request.memory_id,
        section=request.section,
        content=request.content,
        reason=request.reason,
        source=request.source,
        config=app.state.config,
    )


@app.post("/memory/route-storage")
async def route_storage(request: StorageRouteRequest) -> dict[str, Any]:
    ensure_app_state(app)
    if not hasattr(app.state, "route_llm"):
        raise HTTPException(status_code=501, detail="No route_llm is configured yet.")
    decision = route_storage_with_llm(
        content=request.content,
        context=request.context,
        route_llm=app.state.route_llm,
        config=app.state.config,
    )
    return {
        "should_store": decision.should_store,
        "destination": decision.destination,
        "memory_id": decision.memory_id,
        "section": decision.section,
        "reason": decision.reason,
        "content": decision.content,
        "should_write_markdown": decision.should_write_markdown,
        "should_write_rag": decision.should_write_rag,
    }


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    server = config.get("server", {})
    uvicorn.run(
        "main:app",
        host=server.get("host", "127.0.0.1"),
        port=server.get("port", 8000),
        reload=server.get("reload", False),
    )
