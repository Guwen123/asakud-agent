from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass
from typing import Any

from memory.hot_store import get_hot_store
from memory_worker.agent import MemoryWorker
from skill_builder.agent import SkillBuilderWorker


@dataclass(frozen=True)
class BackgroundJob:
    kind: str
    payload: dict[str, Any]


_MANAGER: BackgroundWorkerManager | None = None


class BackgroundWorkerManager:
    """Owns background queues and dispatches work to root-level sub-agents."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.hot_store = get_hot_store(config)
        self.memory_queue: queue.Queue[BackgroundJob] = queue.Queue()
        self.skill_queue: queue.Queue[BackgroundJob] = queue.Queue()
        self._stop = False
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [task for task in self._tasks if not task.done()]
        if self._tasks:
            return
        self._stop = False
        self._tasks = [
            asyncio.create_task(self._run_memory_worker(), name="memory_worker"),
            asyncio.create_task(self._run_skill_builder(), name="skill_builder"),
        ]

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.hot_store = get_hot_store(config)

    async def stop(self) -> None:
        self._stop = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

    def enqueue_memory(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.memory_queue.put(BackgroundJob(kind=kind, payload=payload))
        return {"queued": True, "queue": "memory_worker", "kind": kind}

    def enqueue_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.skill_queue.put(BackgroundJob(kind="skill_build", payload=payload))
        return {"queued": True, "queue": "skill_builder", "kind": "skill_build"}

    async def _run_memory_worker(self) -> None:
        while not self._stop:
            try:
                job = await asyncio.to_thread(self.memory_queue.get, True, 0.5)
            except queue.Empty:
                continue
            try:
                worker = MemoryWorker(self.config, self.hot_store)
                await asyncio.to_thread(worker.process, job)
            except Exception as exc:
                print(f"[memory_worker] error: {exc}")
            finally:
                self.memory_queue.task_done()

    async def _run_skill_builder(self) -> None:
        while not self._stop:
            try:
                job = await asyncio.to_thread(self.skill_queue.get, True, 0.5)
            except queue.Empty:
                continue
            try:
                worker = SkillBuilderWorker(self.config)
                await asyncio.to_thread(worker.process, job)
            except Exception as exc:
                print(f"[skill_builder] error: {exc}")
            finally:
                self.skill_queue.task_done()


def start_background_workers(config: dict[str, Any]) -> BackgroundWorkerManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = BackgroundWorkerManager(config)
    else:
        _MANAGER.update_config(config)
    _MANAGER.start()
    return _MANAGER


async def stop_background_workers() -> None:
    global _MANAGER
    if _MANAGER is None:
        return
    await _MANAGER.stop()
    _MANAGER = None


def enqueue_memory_update(config: dict[str, Any], kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if _MANAGER is None:
        return {"queued": False, "reason": "background_workers_not_started", "kind": kind}
    return _MANAGER.enqueue_memory(kind, payload)


def enqueue_skill_build(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if _MANAGER is None:
        return {"queued": False, "reason": "background_workers_not_started", "kind": "skill_build"}
    return _MANAGER.enqueue_skill(payload)
