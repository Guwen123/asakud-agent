# Sakuro Agent 配置

这是 Agent 的根配置文件。

你可以在 `json` 代码块外写中文说明和备注。程序只解析下面这个 fenced `json` 配置块。

## 配置块

```json
{
  "agent": {
    "name": "sakuro-agent",
    "description": "一个本地运行、支持长期记忆、会话记忆、工具调用和 Skill 的 Agent。",
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
    "api_key":"tp-cz1ic9i3klox7dtpmjortmi5tb1uutc2h29orx27efpf8a32",
    "name": "MiMo-V2.5-Pro",
    "temperature": 0.2,
    "max_output_tokens": 4096,
    "available_models": [
      {
        "name": "MiMo-V2.5-Pro",
        "type": "chat",
        "description": "默认高能力文本模型，适合作为主 Agent 模型。"
      },
      {
        "name": "MiMo-V2.5",
        "type": "chat",
        "description": "通用文本模型，适合普通对话、规划和工具调用。"
      },
      {
        "name": "MiMo-V2-Pro",
        "type": "chat",
        "description": "上一代高能力文本模型，可作为备用模型。"
      },
      {
        "name": "MiMo-V2-Omni",
        "type": "omni",
        "description": "多模态模型，适合后续接入图像、音频等输入。"
      },
      {
        "name": "MiMo-V2.5-TTS",
        "type": "tts",
        "description": "文本转语音模型。"
      },
      {
        "name": "MiMo-V2.5-TTS-VoiceClone",
        "type": "tts",
        "description": "语音克隆 TTS 模型。"
      },
      {
        "name": "MiMo-V2.5-TTS-VoiceDesign",
        "type": "tts",
        "description": "声音设计 TTS 模型。"
      },
      {
        "name": "MiMo-V2-TTS",
        "type": "tts",
        "description": "上一代文本转语音模型。"
      }
    ]
  },
  "paths": {
    "memory_dir": "memory",
    "db_dir": "db",
    "skills_dir": "skills",
    "tools_dir": "tools",
    "database": "db/session_memory.db",
    "schema": "db/session_memory.schema.sql"
  },
  "memory": {
    "markdown_files": [
      {
        "id": "user",
        "path": "memory/USER.md",
        "title": "用户记忆",
        "purpose": "存放稳定的用户画像、偏好、协作方式和边界。",
        "sections": ["偏好", "协作方式", "边界", "禁止记录"]
      },
      {
        "id": "project",
        "path": "memory/MEMORY.md",
        "title": "项目记忆",
        "purpose": "存放稳定的项目事实、运行环境、常见问题和反复出现的修复经验。",
        "sections": ["项目", "环境", "长期说明", "已知修复"]
      },
      {
        "id": "decisions",
        "path": "memory/DECISIONS.md",
        "title": "决策记录",
        "purpose": "存放重要架构选择、原因、取舍和被放弃的方案。",
        "sections": ["当前决策", "被放弃的方案"]
      },
      {
        "id": "scheduled",
        "path": "memory/SCHEDULED_TASKS.md",
        "title": "定时任务",
        "purpose": "存放定时任务的人类可读视图。真正用于执行的状态以 SQLite scheduled_tasks 表为准。",
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
      "purpose": "把未来提醒和定时动作转换为结构化的 scheduled_tasks 记录。"
    },
    {
      "id": "example",
      "path": "skills/example/SKILL.md",
      "title": "示例 Skill",
      "purpose": "展示 Skill 文件的最小格式。"
    }
  ]
}
```

## 中文说明

- `server`：FastAPI 服务配置，`host` 和 `port` 决定服务监听地址。
- `model`：Agent 使用的模型配置。当前配置为兼容 OpenAI 接口协议的 MiMo 服务，密钥直接写在配置块里。
- `paths`：所有运行目录和数据库路径。这里已经统一使用 `db/`，不再使用 `data/`。
- `memory.markdown_files`：需要自动创建的长期记忆 Markdown 文件。
- `memory.sqlite`：需要写入 SQLite 的会话记忆、定时任务和 Skill 执行记录。
- `tools`：Agent 可加载的工具目录和启用列表。
- `skills`：Agent 可加载的 Skill 文件。

修改配置后，运行：

```powershell
python agent_loop\bootstrap.py
```
