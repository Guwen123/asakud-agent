# Sakuro Agent 配置

程序会读取下面 `json` 代码块作为唯一配置源。

```json
{
  "agent": {
    "name": "sakuro-agent",
    "description": "本地运行的长期记忆 Agent。",
    "language": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8000,
    "reload": false,
    "scheduler_interval_seconds": 30
  },
  "model": {
    "provider": "token-plan-cn",
    "protocol": "openai-compatible",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
    "api_key": "tp-cz1ic9i3klox7dtpmjortmi5tb1uutc2h29orx27efpf8a32",
    "name": "MiMo-V2.5-Pro",
    "temperature": 0.2,
    "max_output_tokens": 4096,
    "available_models": [
      {"name": "MiMo-V2.5-Pro", "type": "chat", "description": "默认主模型"},
      {"name": "MiMo-V2.5", "type": "chat", "description": "通用对话模型"},
      {"name": "MiMo-V2-Pro", "type": "chat", "description": "备选高性能模型"},
      {"name": "MiMo-V2-Omni", "type": "omni", "description": "多模态模型"},
      {"name": "MiMo-V2.5-TTS", "type": "tts", "description": "TTS"},
      {"name": "MiMo-V2.5-TTS-VoiceClone", "type": "tts", "description": "语音克隆 TTS"},
      {"name": "MiMo-V2.5-TTS-VoiceDesign", "type": "tts", "description": "语音设计 TTS"},
      {"name": "MiMo-V2-TTS", "type": "tts", "description": "旧版 TTS"}
    ]
  },
  "paths": {
    "memory_dir": "memory",
    "db_dir": "db",
    "skills_dir": "skills",
    "tools_dir": "tools",
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
        "title": "用户记忆",
        "purpose": "用户长期画像与偏好。",
        "sections": ["偏好", "协作方式", "边界", "禁止记录"]
      },
      {
        "id": "project",
        "path": "memory/MEMORY.md",
        "title": "项目记忆",
        "purpose": "长期可复用的经验与习惯。",
        "sections": ["项目事实", "环境", "长期说明", "已知修复"]
      },
      {
        "id": "self",
        "path": "memory/SELF.md",
        "title": "自我认知",
        "purpose": "Agent 对自身能力和工作方式的更新。",
        "sections": ["能力边界", "工作方式", "改进计划"]
      },
      {
        "id": "scheduled",
        "path": "memory/SCHEDULED_TASKS.md",
        "title": "定时任务",
        "purpose": "可读的定时任务视图。",
        "sections": ["进行中", "已完成", "已取消"]
      }
    ],
    "sqlite": {
      "enabled_tables": ["sessions", "messages", "memory_events", "scheduled_tasks", "skill_runs"],
      "enable_message_fts": true
    }
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
    "enabled": ["echo", "time_now"]
  },
  "skills": [
    {
      "id": "scheduled-memory",
      "path": "skills/scheduled-memory/SKILL.md",
      "title": "定时记忆",
      "purpose": "把未来提醒转成结构化任务。"
    },
    {
      "id": "example",
      "path": "skills/example/SKILL.md",
      "title": "示例 Skill",
      "purpose": "Skill 最小模板。"
    }
  ]
}
```
