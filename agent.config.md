# Sakuro Agent Config

The program reads the fenced `json` block below as its runtime configuration.

```json
{
  "agent": {
    "name": "sakuro-agent",
    "description": "Local long-running memory agent.",
    "language": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "reload": false,
    "scheduler_interval_seconds": 30
  },
  "napcat": {
    "enabled": true,
    "http_url": "http://127.0.0.1:3000",
    "token": "${NAPCAT_TOKEN}",
    "callback_path": "/getMessage",
    "reply_path": "/sendMessage",
    "report_format": "string"
  },
  "main_model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2.5-pro",
    "temperature": 0.2,
    "max_output_tokens": 4096
  },
  "route_model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2.5",
    "temperature": 0.0,
    "max_output_tokens": 512
  },
  "multimodal_model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "${MIMO_API_KEY}",
    "name": "mimo-v2-omni",
    "temperature": 0.0,
    "max_output_tokens": 1024
  },
  "paths": {
    "memory_dir": "memory",
    "db_dir": "db",
    "skills_dir": "skills",
    "skill_config_file": "skills/skill.config.md",
    "styles_dir": "styles",
    "style_config_file": "styles/style.config.md",
    "tools_dir": "tools",
    "meme_dir": "meme",
    "database": "db/session_memory.db",
    "schema": "db/session_memory.schema.sql"
  },
  "db": {
    "database": "db/session_memory.db",
    "schema": "db/session_memory.schema.sql",
    "short_term_memory_table": "messages",
    "default_session_id": "default"
  },
  "memory": {
    "markdown_files": [
      {
        "id": "memory",
        "path": "memory/MEMORY.md",
        "title": "Long-Term Memory",
        "purpose": "Stable long-term facts and reusable knowledge.",
        "sections": [
          "Stable Facts"
        ]
      },
      {
        "id": "self",
        "path": "memory/SELF.md",
        "title": "Self Knowledge",
        "purpose": "Durable self-understanding and operating rules for the agent.",
        "sections": [
          "Self Knowledge"
        ]
      },
      {
        "id": "pending",
        "path": "memory/PENDING.md",
        "title": "Pending Facts",
        "purpose": "Facts or clues that still need extraction, validation, or confirmation.",
        "sections": [
          "Pending Facts"
        ]
      },
      {
        "id": "core",
        "path": "memory/CORE.md",
        "title": "Core Archive",
        "purpose": "Archived older SELF/MEMORY entries evicted by token-pressure compaction. CORE uses the same MAX_TOKEN compaction rule.",
        "sections": [
          "Archived Memory"
        ]
      }
    ],
    "forgetting": {
      "enabled": true,
      "max_tokens": 2000,
      "max_tokens_by_id": {
        "memory": 2400,
        "self": 1200,
        "pending": 1200,
        "core": 2400
      },
      "managed_ids": [
        "memory",
        "self",
        "pending",
        "core"
      ],
      "protected_ids": [],
      "history_id": "history",
      "archive_id": "core",
      "archive_source_ids": [
        "memory",
        "self"
      ],
      "max_entries_per_file": 120
    },
    "prompt": {
      "always_markdown_ids": [
        "self",
        "memory",
        "core"
      ],
      "always_routed_markdown_ids": [],
      "routable_markdown_ids": [],
      "load_all_entries_for_ids": [
        "self",
        "memory",
        "core"
      ],
      "always_markdown_sections": {
        "self": [
          "Core Rules"
        ]
      },
      "max_markdown_entries_by_id": {
        "self": 4,
        "memory": 6,
        "core": 3
      },
      "max_markdown_entries": 6,
      "hot_ids": [
        "self",
        "memory",
        "pending"
      ],
      "hot_pending_limit": 8
    },
    "hot_store": {
      "flush_min_session_turns": 5,
      "flush_min_age_seconds": 86400,
      "flush_ids": [
        "self",
        "memory",
        "pending"
      ],
      "prompt_pending_limit": 8,
      "prompt_include_ids": [
        "self",
        "memory",
        "pending"
      ],
      "write_through_without_redis": false
    },
    "sqlite": {
      "enabled_tables": [
        "sessions",
        "messages",
        "memory_events",
        "scheduled_tasks",
        "skill_runs"
      ],
      "enable_message_fts": true
    }
  },
  "recent_summary": {
    "path": "memory/RECENT_SUMMARY.md",
    "max_tokens": 1800,
    "target_tokens": 900,
    "prompt_max_chars": 4000
  },
  "redis": {
    "enabled": true,
    "url": "redis://localhost:6379/0",
    "namespace": "asakud-agent",
    "ttl_seconds": 604800,
    "access_ttl_seconds": 2592000,
    "lock_ttl_ms": 30000
  },
  "style": {
    "enabled": true,
    "default": "atri",
    "temperature": 0.0,
    "max_output_tokens": 2048,
    "styles": {}
  },
  "skill_builder": {
    "temperature": 0.0,
    "max_output_tokens": 4096,
    "templates_dir": "skills/_templates",
    "max_template_chars": 6000
  },
  "meme": {
    "metadata_path": "meme/memes.json",
    "image_dir": "meme/data",
    "auto_collect_probability": 0.35,
    "send_probability": 0.25
  },
  "mcp": {
    "enabled": false,
    "default_server": "",
    "use_default_server": false,
    "servers": [
      {
        "name": "local-mcp-example",
        "enabled": false,
        "base_url": "http://127.0.0.1:9000",
        "transport": "mcp-jsonrpc",
        "endpoint": "/mcp",
        "timeout_seconds": 5,
        "headers": {},
        "notes": "Disabled example only. Enable it only after you start a real MCP HTTP / Streamable HTTP gateway on this address, or add a real server from the dashboard."
      }
    ]
  },
  "loop": {
    "max_steps": 30,
    "load_markdown_memory_on_start": true,
    "short_term_max_messages": 20,
    "short_term_keep_recent": 8,
    "require_confirmation_for": [
      "delete_files",
      "run_destructive_commands",
      "send_external_messages",
      "spend_money"
    ]
  },
  "tools": {
    "directory": "tools",
    "auto_load": true,
    "enabled": [
      "fetch_web"
    ]
  }
}
```
