# MCP Server 配置要点

## 字段口径

- `mcpServers`: 常见客户端配置的顶层对象，用于声明多个 MCP Server。
- 服务名：通常是 `mcpServers` 下的 key，例如 `filesystem`、`github`、`my-server`。
- 本地 `stdio`: 常用字段是 `command`、`args`、`env`。
- 远程 HTTP: 常用字段是 `type` 或 `transport`、`url`、`headers` 或认证配置。

## 传输方式

- 本地开发、命令行包、脚本型 MCP Server：优先用 `stdio`。
- 云端或第三方托管 MCP Server：优先核对是否使用 `streamable-http`。
- SSE / HTTP+SSE 多用于旧版本或兼容场景，回答时应避免把它作为默认推荐。

## 认证与安全

- 本地服务的 API Key 优先通过 `env` 注入。
- 远程服务常见认证方式是 `Authorization: Bearer <token>`。
- 不要要求用户把真实密钥写入示例；使用 `your-key`、`your-token` 等占位符。

## 推荐回答结构

1. 一句话结论：本地配 `command + args + env`，远程配 `type + url + headers/auth`。
2. 通用字段。
3. 本地 stdio 示例。
4. 远程 HTTP 示例。
5. 兼容性或安全注意事项。
