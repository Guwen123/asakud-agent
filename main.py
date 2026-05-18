from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from pydantic import BaseModel

from agent_loop.bootstrap import bootstrap
from agent_loop.config_loader import load_config
from agent_loop.loop import run_agent_once_async
from agent_loop.scheduler import MarkdownTaskScheduler
from http_client import AsyncHttpClient


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    output: str


async def scheduled_task_loop(app: FastAPI) -> None:
    while True:
        interval = app.state.config.get("server", {}).get("scheduler_interval_seconds", 30)
        try:
            await app.state.scheduler.tick()
        except Exception as exc:  # keep scheduler alive
            print(f"[scheduler_loop] error: {exc}")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    app.state.config = load_config()
    app.state.http_client = AsyncHttpClient()
    await app.state.http_client.start()
    app.state.scheduler = MarkdownTaskScheduler(
        app.state.config,
        execute_task=_execute_scheduled_task,
    )
    app.state.scheduler_task = asyncio.create_task(scheduled_task_loop(app), name="scheduler_loop")
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


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    output = await run_agent_once_async(request.message)
    return ChatResponse(output=output)


async def _execute_scheduled_task(task_content: str) -> None:
    # Treat scheduled content as a user trigger to the agent loop.
    await run_agent_once_async(task_content)


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
