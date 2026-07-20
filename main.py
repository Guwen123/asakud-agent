from __future__ import annotations

import asyncio
import ctypes
import json
import os
import platform
import re
import shutil
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_loop.background import start_background_workers, stop_background_workers
from agent_loop.bootstrap import bootstrap
from agent_loop.config_loader import load_config, load_raw_config, project_path
from agent_loop.loop import run_agent_once_async
from agent_loop.nodes.skills import load_skill_registry, write_skill_registry
from agent_loop.observability import performance_snapshot
from db.runtime import RuntimeStore
from tools.mcp.factory import DEFAULT_MCP_SERVER, configured_mcp_servers, list_mcp_server_tools


class SendMessageRequest(BaseModel):
    message_type: str = "private"
    user_id: int | None = None
    group_id: int | None = None
    message: str
    image_ref: str | None = None


class MCPServerRequest(BaseModel):
    name: str = "local"
    base_url: str
    enabled: bool = True
    transport: str = "mcp-jsonrpc"
    endpoint: str | None = None
    timeout_seconds: float = 5.0
    authorization: str | None = None
    headers: dict[str, str] | None = None
    tools_path: str | None = None
    call_path: str | None = None


class NapCatSettingsRequest(BaseModel):
    enabled: bool = True
    http_url: str = "http://127.0.0.1:3000"
    token: str = ""
    callback_path: str = "/getMessage"
    reply_path: str = "/sendMessage"
    report_format: str = "string"


class LLMModelConfigRequest(BaseModel):
    provider: str = "custom"
    protocol: str = "openai-compatible"
    base_url: str
    api_key: str
    name: str
    temperature: float = 0.0
    max_output_tokens: int = 2048


class LLMSettingsRequest(BaseModel):
    main_model: LLMModelConfigRequest
    route_model: LLMModelConfigRequest
    multimodal_model: LLMModelConfigRequest


class ModelDiscoveryRequest(BaseModel):
    provider: str = "custom"
    protocol: str = "openai-compatible"
    base_url: str
    api_key: str


class PackageEnabledRequest(BaseModel):
    enabled: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    app.state.config = load_config()
    app.state.started_at = time.time()
    app.state.background_workers = start_background_workers(app.state.config)
    try:
        yield
    finally:
        await stop_background_workers()


app = FastAPI(
    title="asakud-agent",
    description="Local Web Research Agent service.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/getMessage")
async def get_message(request: Request) -> dict[str, Any]:
    return await _handle_napcat_callback(app, request)


@app.post("/sendMessage")
async def send_message(request: SendMessageRequest) -> dict[str, Any]:
    result = await _send_message(app, request)
    return {"ok": True, "result": result}


async def _handle_napcat_callback(app: FastAPI, request: Request) -> dict[str, Any]:
    try:
        event = await request.json()
    except Exception:
        event = {}

    config = app.state.config
    napcat = config.get("napcat", {})
    if not napcat.get("enabled", False):
        return {"ok": False, "reason": "napcat_disabled"}

    if str(event.get("post_type", "")).lower() != "message":
        return {"ok": True, "ignored": True}
    if _is_self_message(event):
        return {"ok": True, "ignored": True, "reason": "self_message"}

    message_text = _extract_agent_message(event)
    if not message_text.strip():
        return {"ok": True, "ignored": True, "reason": "not_addressed_to_agent"}

    target = _event_to_target(event)

    reply = await run_agent_once_async(message_text, message_target=_target_payload(target))
    send_result = await _send_message(
        app,
        target.copy(
            update={
                "message": reply.get("message", ""),
                "image_ref": reply.get("image_ref", ""),
            }
        ),
    )
    return {"ok": True, "reply": reply, "send_result": send_result}


@app.get("/api/dashboard/status")
async def dashboard_status() -> dict[str, Any]:
    config = app.state.config
    skills = load_skill_registry(config)
    styles = _list_styles(config)
    mcp_servers = _list_mcp_servers(config)
    return {
        "ok": True,
        "agent": {
            "name": config.get("agent", {}).get("name", "asakud-agent"),
            "description": config.get("agent", {}).get("description", ""),
            "language": config.get("agent", {}).get("language", "zh-CN"),
            "timezone": config.get("agent", {}).get("timezone", ""),
            "uptime_seconds": int(time.time() - float(getattr(app.state, "started_at", time.time()))),
        },
        "runtime": {
            "background_workers": bool(getattr(app.state, "background_workers", None)),
            "napcat": bool(config.get("napcat", {}).get("enabled", False)),
            "redis": bool(config.get("redis", {}).get("enabled", False)),
            "tools": config.get("tools", {}).get("enabled", []),
            "skill_count": len(skills),
            "style_count": len(styles),
            "mcp": bool(config.get("mcp", {}).get("enabled", False)),
            "mcp_server_count": len(mcp_servers),
        },
        "computer": _computer_status(),
    }


@app.get("/api/dashboard/performance")
async def dashboard_performance(limit: int = 20) -> dict[str, Any]:
    return performance_snapshot(limit=limit)


@app.get("/api/dashboard/crawls")
async def dashboard_crawls(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    store = _new_runtime_store(app.state.config)
    store.initialize()
    try:
        crawls = store.list_web_crawls(limit=safe_limit)
    finally:
        store.close()
    return {
        "ok": True,
        "count": len(crawls),
        "crawls": [_web_crawl_payload(item) for item in crawls],
    }


@app.get("/api/dashboard/models")
async def dashboard_models() -> dict[str, Any]:
    raw_config = load_raw_config()
    return {
        "ok": True,
        "models": {
            key: _model_config_payload(raw_config, key)
            for key in _model_config_keys()
        },
    }


@app.put("/api/dashboard/models")
async def update_dashboard_models(request: LLMSettingsRequest) -> dict[str, Any]:
    raw_config = load_raw_config()
    raw_config.pop("model", None)
    for key in _model_config_keys():
        raw_config[key] = _normalize_model_config(getattr(request, key), previous=raw_config.get(key, {}))
    _write_runtime_config(raw_config)
    app.state.config = load_config()
    app.state.background_workers = start_background_workers(app.state.config)
    return {
        "ok": True,
        "models": {
            key: _model_config_payload(raw_config, key)
            for key in _model_config_keys()
        },
    }


@app.post("/api/dashboard/models/discover")
async def discover_dashboard_models(request: ModelDiscoveryRequest) -> dict[str, Any]:
    models = await _discover_model_names(request)
    return {"ok": True, "count": len(models), "models": models}


@app.get("/api/dashboard/napcat")
async def dashboard_napcat() -> dict[str, Any]:
    raw_config = load_raw_config()
    return {"ok": True, "napcat": _napcat_payload(raw_config)}


@app.put("/api/dashboard/napcat")
async def update_dashboard_napcat(request: NapCatSettingsRequest) -> dict[str, Any]:
    raw_config = load_raw_config()
    raw_config["napcat"] = _normalize_napcat_config(request)
    _write_runtime_config(raw_config)
    app.state.config = load_config()
    return {"ok": True, "napcat": _napcat_payload(raw_config)}


@app.get("/api/dashboard/skills")
async def dashboard_skills() -> dict[str, Any]:
    config = app.state.config
    return {
        "ok": True,
        "skills": [_skill_payload(item) for item in load_skill_registry(config)],
    }


@app.post("/api/dashboard/skills/upload")
async def upload_skill_package(file: UploadFile = File(...)) -> dict[str, Any]:
    if not _is_zip_upload(file):
        raise HTTPException(status_code=400, detail="Only .zip skill packages are supported.")
    config = app.state.config
    try:
        entry = await _install_skill_zip(config, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "skill": _skill_payload(entry)}


@app.patch("/api/dashboard/skills/{skill_id}")
async def update_skill_enabled(skill_id: str, request: PackageEnabledRequest) -> dict[str, Any]:
    config = app.state.config
    updated = _set_skill_enabled(config, skill_id, request.enabled)
    app.state.config = load_config()
    return {"ok": True, "skill": _skill_payload(updated)}


@app.get("/api/dashboard/styles")
async def dashboard_styles() -> dict[str, Any]:
    return {"ok": True, "styles": _list_styles(app.state.config)}


@app.post("/api/dashboard/styles/upload")
async def upload_style_package(file: UploadFile = File(...)) -> dict[str, Any]:
    if not _is_zip_upload(file):
        raise HTTPException(status_code=400, detail="Only .zip style packages are supported.")
    try:
        style = await _install_style_zip(app.state.config, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "style": style}


@app.patch("/api/dashboard/styles/{style_id}")
async def update_style_enabled(style_id: str, request: PackageEnabledRequest) -> dict[str, Any]:
    config = app.state.config
    updated = _set_style_enabled(config, style_id, request.enabled)
    app.state.config = load_config()
    return {"ok": True, "style": updated}


@app.get("/api/dashboard/mcp")
async def dashboard_mcp() -> dict[str, Any]:
    config = app.state.config
    mcp_cfg = config.get("mcp", {}) if isinstance(config.get("mcp", {}), dict) else {}
    return {
        "ok": True,
        "enabled": bool(mcp_cfg.get("enabled", False)),
        "default_server": str(mcp_cfg.get("default_server", "local") or "local"),
        "servers": _list_mcp_servers(config),
    }


@app.post("/api/dashboard/mcp/servers")
async def add_mcp_server(request: MCPServerRequest) -> dict[str, Any]:
    raw_config = load_raw_config()
    try:
        server = _upsert_mcp_server(raw_config, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_runtime_config(raw_config)
    app.state.config = load_config()
    tool_probe = await asyncio.to_thread(_probe_mcp_server_tools, server)
    return {
        "ok": True,
        "server": _mcp_server_payload(server),
        "tools": tool_probe.get("tools", []),
        "probe_error": tool_probe.get("error", ""),
    }


@app.get("/api/dashboard/mcp/servers/{server_name}/tools")
async def dashboard_mcp_server_tools(server_name: str) -> dict[str, Any]:
    server = _find_mcp_server(app.state.config, server_name)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    tool_probe = await asyncio.to_thread(_probe_mcp_server_tools, server)
    if tool_probe.get("error"):
        return {"ok": False, "server": _mcp_server_payload(server), "tools": [], "error": tool_probe["error"]}
    return {"ok": True, "server": _mcp_server_payload(server), "tools": tool_probe.get("tools", [])}


@app.post("/{napcat_path:path}")
async def napcat_configured_endpoint(napcat_path: str, request: Request) -> dict[str, Any]:
    path = _normalize_api_path(napcat_path)
    napcat_cfg = app.state.config.get("napcat", {})
    callback_path = _normalize_api_path(str(napcat_cfg.get("callback_path", "/getMessage") or "/getMessage"))
    reply_path = _normalize_api_path(str(napcat_cfg.get("reply_path", "/sendMessage") or "/sendMessage"))

    if path == callback_path:
        return await _handle_napcat_callback(app, request)
    if path == reply_path:
        try:
            payload = await request.json()
            send_request = SendMessageRequest(**payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid send message payload.") from exc
        result = await _send_message(app, send_request)
        return {"ok": True, "result": result}

    raise HTTPException(status_code=404, detail="Not found.")


async def _send_message(app: FastAPI, request: SendMessageRequest) -> dict[str, Any]:
    napcat_cfg = app.state.config.get("napcat", {})
    base_url = str(napcat_cfg.get("http_url", "")).rstrip("/")
    token = str(napcat_cfg.get("token", "")).strip()
    if not base_url:
        return {"ok": False, "reason": "missing_http_url"}

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    message_type = str(request.message_type or "private").lower()
    text_message = str(request.message or "").strip()
    image_ref = str(request.image_ref or "").strip().replace("\\", "/")

    if message_type == "group":
        endpoint = "/send_group_msg"

        def build_body(message: str) -> dict[str, Any]:
            return {"group_id": request.group_id, "message": message}

    else:
        endpoint = "/send_private_msg"

        def build_body(message: str) -> dict[str, Any]:
            return {"user_id": request.user_id, "message": message}

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=headers) as client:
        results: dict[str, Any] = {}
        if text_message:
            resp = await client.post(endpoint, json=build_body(text_message))
            resp.raise_for_status()
            results["text"] = resp.json() if resp.content else {"ok": True}
        if image_ref:
            image_message = f"[CQ:image,file={image_ref}]"
            resp = await client.post(endpoint, json=build_body(image_message))
            resp.raise_for_status()
            results["image"] = resp.json() if resp.content else {"ok": True}
        return results or {"ok": False, "reason": "empty_message"}


def _computer_status() -> dict[str, Any]:
    total_memory, used_memory = _memory_snapshot()
    disk = shutil.disk_usage(project_path("."))
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or platform.machine(),
        "pid": os.getpid(),
        "cpu": {
            "cores": os.cpu_count() or 0,
            "load_average": _load_average(),
        },
        "memory": {
            "total_mb": _bytes_to_mb(total_memory),
            "used_mb": _bytes_to_mb(used_memory),
            "percent": round((used_memory / total_memory) * 100, 1) if total_memory else None,
        },
        "disk": {
            "total_mb": _bytes_to_mb(disk.total),
            "used_mb": _bytes_to_mb(disk.used),
            "percent": round((disk.used / disk.total) * 100, 1) if disk.total else None,
        },
    }


def _memory_snapshot() -> tuple[int, int]:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = int(status.ullTotalPhys)
            available = int(status.ullAvailPhys)
            return total, max(total - available, 0)
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values: dict[str, int] = {}
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                values[parts[0].rstrip(":")] = int(parts[1]) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        return total, max(total - available, 0)
    return 0, 0


def _load_average() -> list[float]:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        return []


def _bytes_to_mb(value: int) -> float:
    return round(float(value) / 1024 / 1024, 2) if value else 0.0


def _skill_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "") or ""),
        "summary": str(item.get("summary", "") or ""),
        "path": str(item.get("path", "") or ""),
        "type": str(item.get("type", "workflow") or "workflow"),
        "tools": item.get("tools", []),
        "references": item.get("references", []),
        "entry": str(item.get("entry", "") or ""),
        "max_steps": item.get("max_steps", 8),
        "enabled": bool(item.get("enabled", True)),
    }


def _set_skill_enabled(config: dict[str, Any], skill_id: str, enabled: bool) -> dict[str, Any]:
    normalized = _slugify(skill_id)
    if not normalized:
        raise HTTPException(status_code=400, detail="skill_id is required.")

    registry = load_skill_registry(config)
    updated: dict[str, Any] | None = None
    for item in registry:
        if _slugify(str(item.get("id", "") or "")) == normalized:
            item["enabled"] = bool(enabled)
            updated = item
            break

    if updated is None:
        raise HTTPException(status_code=404, detail="Skill not found.")

    write_skill_registry(config, registry)
    return updated


def _model_config_keys() -> tuple[str, str, str]:
    return ("main_model", "route_model", "multimodal_model")


def _model_config_payload(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if key == "main_model" and not isinstance(value, dict):
        value = config.get("model")
    model = value if isinstance(value, dict) else {}
    return {
        "provider": str(model.get("provider", "custom") or "custom"),
        "protocol": str(model.get("protocol", "openai-compatible") or "openai-compatible"),
        "base_url": str(model.get("base_url", "") or ""),
        "api_key": str(model.get("api_key", "") or ""),
        "name": str(model.get("name", "") or ""),
        "temperature": _safe_float(model.get("temperature"), 0.0),
        "max_output_tokens": _safe_int(model.get("max_output_tokens"), 2048),
    }


def _normalize_model_config(request: LLMModelConfigRequest, *, previous: Any) -> dict[str, Any]:
    _ = previous
    base_url = str(request.base_url or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Model base_url must be an http(s) URL.")

    name = str(request.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Model name is required.")

    api_key = str(request.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Model api_key is required.")
    if _looks_like_env_placeholder(api_key) or _looks_like_env_placeholder(base_url):
        raise HTTPException(
            status_code=400,
            detail="Model base_url and api_key must be entered directly from the dashboard, not as ${ENV_VAR} placeholders.",
        )

    return {
        "provider": str(request.provider or "custom").strip() or "custom",
        "protocol": str(request.protocol or "openai-compatible").strip() or "openai-compatible",
        "base_url": base_url,
        "api_key": api_key,
        "name": name,
        "temperature": _safe_float(request.temperature, 0.0),
        "max_output_tokens": max(_safe_int(request.max_output_tokens, 2048), 1),
    }


async def _discover_model_names(request: ModelDiscoveryRequest) -> list[str]:
    base_url = str(request.base_url or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Model base_url must be an http(s) URL.")

    api_key = str(request.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Model api_key is required.")
    if _looks_like_env_placeholder(api_key) or _looks_like_env_placeholder(base_url):
        raise HTTPException(
            status_code=400,
            detail="Model base_url and api_key must be entered directly before discovering models.",
        )

    models_url = _model_list_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await client.get(models_url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 400
        detail = _safe_http_error_detail(exc.response)
        raise HTTPException(status_code=400, detail=f"Model discovery failed with HTTP {status_code}: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Model discovery failed: {type(exc).__name__}: {exc}") from exc

    models = _extract_model_names(payload)
    if not models:
        raise HTTPException(status_code=400, detail="No models were found in the provider response.")
    return models


def _model_list_url(base_url: str) -> str:
    text = str(base_url or "").strip().rstrip("/")
    if text.endswith("/models"):
        return text
    if text.endswith("/chat/completions"):
        return text[: -len("/chat/completions")] + "/models"
    if text.endswith("/responses"):
        return text[: -len("/responses")] + "/models"
    return f"{text}/models"


def _extract_model_names(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        candidates = payload.get("data")
        if candidates is None:
            candidates = payload.get("models")
        if candidates is None:
            candidates = payload.get("model")
    else:
        candidates = payload

    values: list[str] = []
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
                if model_id:
                    values.append(model_id)
    elif isinstance(candidates, dict):
        for key, value in candidates.items():
            if isinstance(value, dict):
                model_id = str(value.get("id") or value.get("name") or key).strip()
                if model_id:
                    values.append(model_id)
            elif isinstance(value, str):
                values.append(value)

    return sorted({value for value in values if value})


def _safe_http_error_detail(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
    except Exception:
        return response.text[:300]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or payload)[:300]
        if error:
            return str(error)[:300]
        message = payload.get("message")
        if message:
            return str(message)[:300]
    return str(payload)[:300]


def _napcat_payload(config: dict[str, Any]) -> dict[str, Any]:
    napcat = config.get("napcat", {})
    if not isinstance(napcat, dict):
        napcat = {}
    return {
        "enabled": bool(napcat.get("enabled", False)),
        "http_url": str(napcat.get("http_url", "") or ""),
        "token": str(napcat.get("token", "") or ""),
        "callback_path": str(napcat.get("callback_path", "/getMessage") or "/getMessage"),
        "reply_path": str(napcat.get("reply_path", "/sendMessage") or "/sendMessage"),
        "report_format": str(napcat.get("report_format", "string") or "string"),
    }


def _normalize_napcat_config(request: NapCatSettingsRequest) -> dict[str, Any]:
    http_url = str(request.http_url or "").strip().rstrip("/")
    if request.enabled:
        parsed = urlparse(http_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="NapCat http_url must be an http(s) URL when enabled.")
    report_format = str(request.report_format or "string").strip().lower()
    if report_format not in {"string", "array"}:
        report_format = "string"
    return {
        "enabled": bool(request.enabled),
        "http_url": http_url,
        "token": str(request.token or "").strip(),
        "callback_path": _normalize_api_path(request.callback_path or "/getMessage") or "/getMessage",
        "reply_path": _normalize_api_path(request.reply_path or "/sendMessage") or "/sendMessage",
        "report_format": report_format,
    }


def _list_mcp_servers(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [_mcp_server_payload(server) for server in configured_mcp_servers(config)]


def _mcp_server_payload(server: dict[str, Any]) -> dict[str, Any]:
    headers = server.get("headers", {})
    list_req = server.get("list_tools_request", {})
    call_req = server.get("call_tool_request", {})
    tools_path = str(server.get("tools_path", "") or "")
    call_path = str(server.get("call_path", "") or "")
    if not tools_path and isinstance(list_req, dict):
        tools_path = str(list_req.get("path", "") or "")
    if not call_path and isinstance(call_req, dict):
        call_path = str(call_req.get("path", "") or "")
    return {
        "name": _slugify(str(server.get("name", "") or "local")) or "local",
        "enabled": bool(server.get("enabled", True)),
        "base_url": str(server.get("base_url", "") or ""),
        "transport": str(server.get("transport", "mcp-jsonrpc") or "mcp-jsonrpc"),
        "endpoint": str(server.get("endpoint", "") or ""),
        "timeout_seconds": float(server.get("timeout_seconds", 10) or 10),
        "tools_path": tools_path,
        "call_path": call_path,
        "has_auth": bool(isinstance(headers, dict) and headers.get("Authorization")),
        "notes": str(server.get("notes", "") or ""),
    }


def _upsert_mcp_server(config: dict[str, Any], request: MCPServerRequest) -> dict[str, Any]:
    mcp_cfg = config.setdefault("mcp", {})
    if not isinstance(mcp_cfg, dict):
        raise ValueError("mcp config must be an object.")
    servers = mcp_cfg.setdefault("servers", [])
    if not isinstance(servers, list):
        servers = []
        mcp_cfg["servers"] = servers

    server_name = _slugify(request.name) or "local"
    transport = _normalize_mcp_transport(request.transport)
    base_url, endpoint = _normalize_mcp_url(request.base_url, request.endpoint, transport)
    headers = {str(key): str(value) for key, value in (request.headers or {}).items() if str(key).strip()}
    auth_header = _authorization_header(request.authorization)
    if auth_header:
        headers["Authorization"] = auth_header

    server: dict[str, Any] = {
        "name": server_name,
        "enabled": bool(request.enabled),
        "base_url": base_url,
        "transport": transport,
        "endpoint": endpoint,
        "timeout_seconds": max(float(request.timeout_seconds or 5.0), 1.0),
        "headers": headers,
    }
    if transport == "simple-http":
        server["list_tools_request"] = {
            "method": "GET",
            "path": _normalize_api_path(request.tools_path or "/tools"),
        }
        server["call_tool_request"] = {
            "method": "POST",
            "path": _normalize_api_path(request.call_path or "/tools/call"),
        }

    updated = False
    for index, item in enumerate(servers):
        if not isinstance(item, dict):
            continue
        if _slugify(str(item.get("name", "") or "")) == server_name:
            servers[index] = server
            updated = True
            break
    if not updated:
        servers.append(server)

    mcp_cfg["enabled"] = True
    mcp_cfg["default_server"] = str(mcp_cfg.get("default_server", server_name) or server_name)
    tools_cfg = config.setdefault("tools", {})
    enabled_tools = tools_cfg.setdefault("enabled", [])
    if not isinstance(enabled_tools, list):
        enabled_tools = []
        tools_cfg["enabled"] = enabled_tools
    if "mcp" not in enabled_tools:
        enabled_tools.append("mcp")
    if "fetch_web" not in enabled_tools:
        enabled_tools.insert(0, "fetch_web")
    return server


def _find_mcp_server(config: dict[str, Any], server_name: str) -> dict[str, Any] | None:
    normalized = _slugify(server_name)
    for server in configured_mcp_servers(config):
        if _slugify(str(server.get("name", "") or "")) == normalized:
            return server
    return None


def _probe_mcp_server_tools(server: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"tools": list_mcp_server_tools(server)}
    except Exception as exc:
        return {"tools": [], "error": str(exc)}


def _normalize_mcp_transport(value: str) -> str:
    text = str(value or "mcp-jsonrpc").strip().lower().replace("_", "-")
    if text in {"jsonrpc", "mcp", "streamable-http", "streamable"}:
        return "mcp-jsonrpc"
    if text in {"simple", "simple-http", "rest"}:
        return "simple-http"
    return "mcp-jsonrpc"


def _normalize_mcp_url(raw_url: str, raw_endpoint: str | None, transport: str) -> tuple[str, str]:
    raw = str(raw_url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("MCP base_url must be an http(s) URL.")
    base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
    path_from_url = parsed.path.strip()
    if raw_endpoint is not None and str(raw_endpoint).strip():
        endpoint = _normalize_api_path(str(raw_endpoint))
    elif path_from_url and path_from_url != "/":
        endpoint = _normalize_api_path(path_from_url)
    elif transport == "mcp-jsonrpc":
        endpoint = "/mcp"
    else:
        endpoint = ""
    return base_url, endpoint


def _normalize_api_path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("/") else f"/{text}"


def _authorization_header(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.lower().startswith("bearer ") else f"Bearer {text}"


def _looks_like_env_placeholder(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("${") and text.endswith("}")


def _read_style_registry(config: dict[str, Any]) -> dict[str, Any]:
    path = project_path(config.get("paths", {}).get("style_config_file", "styles/style.config.md"))
    if not path.exists():
        return {"default": str(config.get("style", {}).get("default", "atri") or "atri"), "styles": []}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    raw = match.group(1) if match else text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"default": str(config.get("style", {}).get("default", "atri") or "atri"), "styles": []}
    if not isinstance(data, dict):
        return {"default": str(config.get("style", {}).get("default", "atri") or "atri"), "styles": []}
    if not isinstance(data.get("styles"), list):
        data["styles"] = []
    data.setdefault("default", str(config.get("style", {}).get("default", "atri") or "atri"))
    return data


def _write_style_registry(config: dict[str, Any], registry: dict[str, Any]) -> None:
    path = project_path(config.get("paths", {}).get("style_config_file", "styles/style.config.md"))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default": str(registry.get("default", "atri") or "atri"),
        "styles": [
            item
            for item in registry.get("styles", [])
            if isinstance(item, dict) and _slugify(str(item.get("id", "") or ""))
        ],
    }
    content = "# Style Registry\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n"
    path.write_text(content, encoding="utf-8")


def _list_styles(config: dict[str, Any]) -> list[dict[str, Any]]:
    registry = _read_style_registry(config)
    default_id = _slugify(str(registry.get("default", "") or config.get("style", {}).get("default", "atri")))
    result: list[dict[str, Any]] = []
    for item in registry.get("styles", []):
        if not isinstance(item, dict):
            continue
        payload = _style_payload(item, default_id)
        if payload:
            result.append(payload)
    return result


def _style_payload(item: dict[str, Any], default_id: str = "") -> dict[str, Any]:
    style_id = _slugify(str(item.get("id", "") or ""))
    if not style_id:
        return {}
    return {
        "id": style_id,
        "name": str(item.get("name", style_id) or style_id),
        "type": str(item.get("type", "custom") or "custom"),
        "summary": str(item.get("summary", "") or item.get("guide", "") or ""),
        "path": str(item.get("path", "") or item.get("skill_path", "") or ""),
        "default": bool(default_id and style_id == default_id),
        "source": str(item.get("source", "") or ("guide" if item.get("guide") else "skill")),
        "enabled": bool(item.get("enabled", True)),
    }


def _set_style_enabled(config: dict[str, Any], style_id: str, enabled: bool) -> dict[str, Any]:
    normalized = _slugify(style_id)
    if not normalized:
        raise HTTPException(status_code=400, detail="style_id is required.")

    registry = _read_style_registry(config)
    default_id = _slugify(str(registry.get("default", "") or config.get("style", {}).get("default", "atri")))
    updated: dict[str, Any] | None = None
    for item in registry.get("styles", []):
        if not isinstance(item, dict):
            continue
        if _slugify(str(item.get("id", "") or "")) == normalized:
            item["enabled"] = bool(enabled)
            updated = item
            break

    if updated is None:
        raise HTTPException(status_code=404, detail="Style not found.")

    _write_style_registry(config, registry)
    return _style_payload(updated, default_id)


def _is_zip_upload(file: UploadFile) -> bool:
    filename = str(file.filename or "").lower()
    return filename.endswith(".zip")


async def _install_skill_zip(config: dict[str, Any], file: UploadFile) -> dict[str, Any]:
    package_root, metadata = await _unpack_skill_like_zip(file)
    try:
        slug = _unique_slug(project_path(config.get("paths", {}).get("skills_dir", "skills")) / "imported", _package_id(file, package_root, metadata))
        target_root = project_path(config.get("paths", {}).get("skills_dir", "skills")) / "imported" / slug
        shutil.copytree(package_root, target_root)

        skill_path = target_root / "SKILL.md"
        entry = {
            "id": slug,
            "summary": str(metadata.get("summary", "") or _read_first_heading(skill_path) or slug),
            "path": _relative_project_path(skill_path),
            "type": str(metadata.get("type", "workflow") or "workflow"),
            "enabled": True,
        }
        for key in ("entry", "tools", "references", "max_steps"):
            if key in metadata and metadata[key] not in ("", None, [], {}):
                entry[key] = metadata[key]

        registry = [item for item in load_skill_registry(config) if item.get("id") != slug]
        registry.append(entry)
        write_skill_registry(config, registry)
        return entry
    finally:
        _cleanup_upload_tree(package_root)


async def _install_style_zip(config: dict[str, Any], file: UploadFile) -> dict[str, Any]:
    package_root, metadata = await _unpack_skill_like_zip(file)
    try:
        styles_root = project_path(config.get("paths", {}).get("styles_dir", "styles")) / "imported"
        slug = _unique_slug(styles_root, _package_id(file, package_root, metadata))
        target_root = styles_root / slug
        shutil.copytree(package_root, target_root)

        skill_path = target_root / "SKILL.md"
        registry = _read_style_registry(config)
        styles = [item for item in registry.get("styles", []) if _slugify(str(item.get("id", "") or "")) != slug]
        style_entry = {
            "id": slug,
            "name": str(metadata.get("name", "") or _read_first_heading(skill_path) or slug),
            "type": str(metadata.get("type", "custom") or "custom"),
            "summary": str(metadata.get("summary", "") or ""),
            "path": _relative_project_path(skill_path),
            "source": "skill",
            "enabled": True,
        }
        styles.append(style_entry)
        registry["styles"] = styles
        registry.setdefault("default", str(config.get("style", {}).get("default", "atri") or "atri"))
        _write_style_registry(config, registry)
        return _style_payload(style_entry, _slugify(str(registry.get("default", "atri"))))
    finally:
        _cleanup_upload_tree(package_root)


async def _unpack_skill_like_zip(file: UploadFile) -> tuple[Path, dict[str, Any]]:
    data = await file.read()
    if not data:
        raise ValueError("Uploaded zip is empty.")
    temp_dir = Path(tempfile.mkdtemp(prefix="asakud-upload-"))
    zip_path = temp_dir / "package.zip"
    zip_path.write_bytes(data)
    extract_root = temp_dir / "extract"
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract_zip(archive, extract_root)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError("Invalid zip package.") from exc
    except ValueError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    skill_files = [
        path
        for path in extract_root.rglob("SKILL.md")
        if "__MACOSX" not in path.parts and path.is_file()
    ]
    if not skill_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError("Zip package must contain a SKILL.md file.")
    package_root = skill_files[0].parent
    metadata = _read_package_metadata(package_root)
    return package_root, metadata


def _safe_extract_zip(archive: zipfile.ZipFile, target: Path) -> None:
    target_root = target.resolve()
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        destination = (target / name).resolve()
        if target_root not in destination.parents and destination != target_root:
            raise ValueError("Zip package contains an unsafe path.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("wb") as handle:
            shutil.copyfileobj(source, handle)


def _read_package_metadata(package_root: Path) -> dict[str, Any]:
    for name in ("skill.json", "style.json"):
        path = package_root / name
        if path.exists() and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _cleanup_upload_tree(package_root: Path) -> None:
    for parent in [package_root, *package_root.parents]:
        if parent.name.startswith("asakud-upload-"):
            shutil.rmtree(parent, ignore_errors=True)
            return


def _package_id(file: UploadFile, package_root: Path, metadata: dict[str, Any]) -> str:
    return _slugify(str(metadata.get("id", "") or package_root.name or file.filename or "package"))


def _unique_slug(root: Path, base: str) -> str:
    root.mkdir(parents=True, exist_ok=True)
    slug = _slugify(base) or "package"
    candidate = slug
    index = 2
    while (root / candidate).exists():
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    return re.sub(r"-{2,}", "-", normalized).strip("-")


def _read_first_heading(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _relative_project_path(path: Path) -> str:
    root = project_path(".").resolve()
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _write_runtime_config(config: dict[str, Any]) -> None:
    config_path = project_path("agent.config.md")
    text = config_path.read_text(encoding="utf-8")
    rendered = json.dumps(config, ensure_ascii=False, indent=2)
    updated = re.sub(
        r"```json\s*(\{.*?\})\s*```",
        lambda _match: f"```json\n{rendered}\n```",
        text,
        count=1,
        flags=re.DOTALL,
    )
    config_path.write_text(updated, encoding="utf-8")


def _new_runtime_store(config: dict[str, Any]) -> RuntimeStore:
    db_config = dict(config.get("db", {}))
    paths_config = dict(config.get("paths", {}))
    db_config.setdefault("database", paths_config.get("database", "db/session_memory.db"))
    db_config.setdefault("schema", paths_config.get("schema", "db/session_memory.schema.sql"))
    return RuntimeStore(project_path(db_config["database"]), project_path(db_config["schema"]))


def _web_crawl_payload(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "query": record.query,
        "result": record.result,
        "ok": record.ok,
        "error": record.error or "",
        "created_at": record.created_at,
        "metadata": record.metadata or {},
    }


def _extract_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        chunks: list[str] = []
        for seg in message:
            if not isinstance(seg, dict):
                continue
            data = seg.get("data", {})
            if seg.get("type") == "text" and isinstance(data, dict):
                chunks.append(str(data.get("text", "")))
            elif seg.get("type") == "image" and isinstance(data, dict):
                attrs: list[str] = []
                for key in ("url", "file", "path", "file_path"):
                    value = str(data.get(key, "") or "").strip()
                    if value:
                        attrs.append(f"{key}={value}")
                if attrs:
                    chunks.append(f"[CQ:image,{','.join(attrs)}]")
        return "".join(chunks)
    return str(message or "")


def _extract_agent_message(event: dict[str, Any]) -> str:
    message_type = str(event.get("message_type", "private") or "private").lower()
    message = event.get("message")

    if message_type != "group":
        return _extract_text(message)

    self_id = _to_optional_int(event.get("self_id"))
    if self_id is None:
        return ""

    if isinstance(message, list):
        if not _has_at_segment(message, self_id):
            return ""
        return _strip_at_segments(_extract_text(_filter_non_at_segments(message, self_id)))

    raw_text = _extract_text(message)
    if not _contains_cq_at(raw_text, self_id):
        return ""
    return _strip_at_segments(raw_text, self_id=self_id)


def _has_at_segment(message: list[Any], self_id: int) -> bool:
    target = str(self_id)
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if str(seg.get("type", "")).lower() != "at":
            continue
        data = seg.get("data", {})
        if isinstance(data, dict) and str(data.get("qq", "")).strip() == target:
            return True
    return False


def _filter_non_at_segments(message: list[Any], self_id: int) -> list[Any]:
    target = str(self_id)
    kept: list[Any] = []
    for seg in message:
        if not isinstance(seg, dict):
            kept.append(seg)
            continue
        if str(seg.get("type", "")).lower() != "at":
            kept.append(seg)
            continue
        data = seg.get("data", {})
        qq = str(data.get("qq", "")).strip() if isinstance(data, dict) else ""
        if qq != target:
            kept.append(seg)
    return kept


def _contains_cq_at(text: str, self_id: int) -> bool:
    pattern = re.compile(rf"\[CQ:at,qq={self_id}(?:,[^\]]*)?\]")
    return bool(pattern.search(text))


def _strip_at_segments(text: str, self_id: int | None = None) -> str:
    value = str(text or "")
    if self_id is None:
        value = re.sub(r"\[CQ:at,qq=\d+(?:,[^\]]*)?\]", " ", value)
    else:
        value = re.sub(rf"\[CQ:at,qq={self_id}(?:,[^\]]*)?\]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_self_message(event: dict[str, Any]) -> bool:
    self_id = _to_optional_int(event.get("self_id"))
    user_id = _to_optional_int(event.get("user_id"))
    sender = event.get("sender", {})
    sender_id = _to_optional_int(sender.get("user_id")) if isinstance(sender, dict) else None
    return self_id is not None and (self_id == user_id or self_id == sender_id)


def _event_to_target(event: dict[str, Any]) -> SendMessageRequest:
    return SendMessageRequest(
        message_type=str(event.get("message_type", "private")),
        user_id=_to_optional_int(event.get("user_id")),
        group_id=_to_optional_int(event.get("group_id")),
        message="",
    )


def _target_payload(target: SendMessageRequest) -> dict[str, Any] | None:
    message_type = str(target.message_type or "private").lower()
    if message_type == "group":
        if target.group_id is None:
            return None
        return {"message_type": "group", "group_id": target.group_id}
    if target.user_id is None:
        return None
    return {"message_type": "private", "user_id": target.user_id}


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
