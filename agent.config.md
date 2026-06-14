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
    "token": "bppgWJ0-EeTzhOzg",
    "callback_path": "/getMessage",
    "reply_path": "/sendMessage",
    "report_format": "string"
  },
  "model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "",
    "name": "mimo-v2.5-pro",
    "temperature": 0.2,
    "max_output_tokens": 4096,
    "available_models": [
      {
        "name": "mimo-v2.5-pro",
        "type": "chat",
        "description": "Default chat model."
      },
      {
        "name": "mimo-v2.5",
        "type": "chat",
        "description": "General-purpose chat model."
      },
      {
        "name": "mimo-v2-pro",
        "type": "chat",
        "description": "Alternate high-performance chat model."
      },
      {
        "name": "mimo-v2-omni",
        "type": "omni",
        "description": "Multimodal model."
      },
      {
        "name": "mimo-v2.5-tts",
        "type": "tts",
        "description": "Text-to-speech model."
      },
      {
        "name": "mimo-v2.5-tts-voiceclone",
        "type": "tts",
        "description": "Voice-clone TTS model."
      },
      {
        "name": "mimo-v2.5-tts-voicedesign",
        "type": "tts",
        "description": "Voice-design TTS model."
      },
      {
        "name": "mimo-v2-tts",
        "type": "tts",
        "description": "Legacy TTS model."
      }
    ]
  },
  "route_model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "",
    "name": "mimo-v2.5",
    "temperature": 0.0,
    "max_output_tokens": 512
  },
  "multimodal_model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "",
    "name": "mimo-v2-omni",
    "temperature": 0.0,
    "max_output_tokens": 1024
  },
  "paths": {
    "memory_dir": "memory",
    "db_dir": "db",
    "skills_dir": "skills",
    "skill_config_file": "skills/skill.config.md",
    "tools_dir": "tools",
    "meme_dir": "meme",
    "database": "db/session_memory.db",
    "schema": "db/session_memory.schema.sql",
    "rag_memory_file": "rag/data/long_term_memory.jsonl"
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
        "id": "user",
        "path": "memory/USER.md",
        "title": "User Memory",
        "purpose": "Long-term user preferences and collaboration notes.",
        "sections": [
          "Preferences",
          "Collaboration",
          "Boundaries",
          "Do Not Record"
        ]
      },
      {
        "id": "project",
        "path": "memory/MEMORY.md",
        "title": "Project Memory",
        "purpose": "Reusable long-term project knowledge.",
        "sections": [
          "Project Facts",
          "Environment",
          "Long Term Notes",
          "Known Fixes"
        ]
      },
      {
        "id": "self",
        "path": "memory/SELF.md",
        "title": "Self Memory",
        "purpose": "Long-term updates about how the agent should work.",
        "sections": [
          "Capability Boundaries",
          "Working Style",
          "Improvement Plan"
        ]
      },
      {
        "id": "scheduled",
        "path": "memory/SCHEDULED_TASKS.md",
        "title": "Scheduled Tasks",
        "purpose": "Readable scheduled task list.",
        "sections": [
          "Active",
          "Completed",
          "Cancelled"
        ]
      }
    ],
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
  "meme": {
    "metadata_path": "meme/memes.json",
    "image_dir": "meme/data",
    "auto_collect_probability": 0.35,
    "send_probability": 0.25
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
      "echo",
      "time_now"
    ]
  }
}
```
