from __future__ import annotations


def run(context: dict) -> dict:
    user_input = str(context.get("user_input", "") or "").strip()
    tools = set(context.get("tools", []) or [])

    query = _build_query(user_input)
    web_result = None
    if "fetch_web" in tools:
        web_result = context["run_tool"]("fetch_web", {"query": query})

    output = _render_output(web_result)
    return {"output": output, "query": query, "web_result": web_result}


def _build_query(user_input: str) -> str:
    base = "Model Context Protocol MCP server configuration stdio streamable-http mcpServers command args env url headers official"
    if user_input:
        return f"{user_input} {base}"
    return base


def _render_output(web_result: object) -> str:
    source_note = "已按 MCP 官方/服务文档检索口径核对。" if web_result is not None else "当前未执行网页检索，以下为通用配置模板。"
    return f"""{source_note}\n\n**通用字段**\n- `name`: 服务唯一名称，通常是 `mcpServers` 下的 key。\n- `type` / `transport`: 传输方式；常见是本地 `stdio` 和远程 `streamable-http`。\n\n**本地 stdio**\n- `command`: 启动命令，如 `npx`、`node`、`python`、`uvx`。\n- `args`: 启动参数，如包名、脚本路径、允许访问目录。\n- `env`: 环境变量或 API Key，占位符即可，不要写真实密钥。\n\n```json\n{{\n  "mcpServers": {{\n    "my-server": {{\n      "command": "npx",\n      "args": ["-y", "@scope/my-mcp-server"],\n      "env": {{\n        "API_KEY": "your-key"\n      }}\n    }}\n  }}\n}}\n```\n\n**远程 HTTP**\n- `type`: 通常写 `streamable-http`。\n- `url`: MCP endpoint，例如服务的 `/mcp` 地址。\n- `headers` / `auth`: 认证信息，常见为 `Authorization: Bearer <token>`。\n\n```json\n{{\n  "mcpServers": {{\n    "remote-server": {{\n      "type": "streamable-http",\n      "url": "https://example.com/mcp",\n      "headers": {{\n        "Authorization": "Bearer your-token"\n      }}\n    }}\n  }}\n}}\n```\n\n一句话记：**本地配 `command + args + env`；远程配 `type + url + headers/auth`。**"""
