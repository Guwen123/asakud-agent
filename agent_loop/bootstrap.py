from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

try:
    from .config_loader import load_config, project_path
except ImportError:
    from config_loader import load_config, project_path


TABLE_SQL: dict[str, str] = {
    "sessions": """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  title TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  metadata_json TEXT
);
""",
    "messages": """
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
""",
    "memory_events": """
CREATE TABLE IF NOT EXISTS memory_events (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  memory_type TEXT NOT NULL,
  content TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  applied_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  metadata_json TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);
""",
    "scheduled_tasks": """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  trigger_at TEXT NOT NULL,
  timezone TEXT NOT NULL,
  repeat_type TEXT NOT NULL DEFAULT 'none',
  repeat_rule TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_triggered_at TEXT,
  result_json TEXT,
  metadata_json TEXT
);
""",
    "skill_runs": """
CREATE TABLE IF NOT EXISTS skill_runs (
  id TEXT PRIMARY KEY,
  skill_name TEXT NOT NULL,
  session_id TEXT,
  input_json TEXT,
  output_json TEXT,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);
""",
}


INDEX_SQL: dict[str, str] = {
    "messages": """
CREATE INDEX IF NOT EXISTS idx_messages_session_created
ON messages(session_id, created_at);
""",
    "memory_events": """
CREATE INDEX IF NOT EXISTS idx_memory_events_type_status
ON memory_events(memory_type, status);
""",
    "scheduled_tasks": """
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status_trigger
ON scheduled_tasks(status, trigger_at);
""",
}


FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  content,
  message_id UNINDEXED,
  session_id UNINDEXED
);

CREATE TRIGGER IF NOT EXISTS messages_ai
AFTER INSERT ON messages
BEGIN
  INSERT INTO messages_fts(content, message_id, session_id)
  VALUES (new.content, new.id, new.session_id);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad
AFTER DELETE ON messages
BEGIN
  DELETE FROM messages_fts WHERE message_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS messages_au
AFTER UPDATE ON messages
BEGIN
  DELETE FROM messages_fts WHERE message_id = old.id;
  INSERT INTO messages_fts(content, message_id, session_id)
  VALUES (new.content, new.id, new.session_id);
END;
"""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_if_missing(path: Path, content: str) -> bool:
    ensure_parent(path)
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def render_markdown_memory(item: dict[str, Any]) -> str:
    lines = [
        f"# {item['title']}",
        "",
        item.get("purpose", ""),
        "",
    ]
    for section in item.get("sections", []):
        lines.extend([f"## {section}", "", "- 暂无。", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_skill(item: dict[str, Any]) -> str:
    return f"""# {item['title']}

适用场景：{item.get('purpose', '未配置用途。')}

## 输入

- 在这里描述这个 Skill 需要的输入。

## 工作流

1. 判断这个 Skill 是否适用。
2. 收集必要上下文。
3. 执行可复用步骤。
4. 验证结果。

## 验证

- 描述另一个 Agent 如何确认这个 Skill 已经正确执行。
"""


def build_schema(config: dict[str, Any]) -> str:
    sqlite_config = config["memory"]["sqlite"]
    enabled_tables = sqlite_config.get("enabled_tables", [])
    parts = ["PRAGMA foreign_keys = ON;\n"]

    for table in enabled_tables:
        if table not in TABLE_SQL:
            raise ValueError(f"Unknown table in config: {table}")
        parts.append(TABLE_SQL[table])

    for table in enabled_tables:
        if table in INDEX_SQL:
            parts.append(INDEX_SQL[table])

    if "messages" in enabled_tables and sqlite_config.get("enable_message_fts", False):
        parts.append(FTS_SQL)

    return "\n".join(parts).strip() + "\n"


def bootstrap_meme_storage(config: dict[str, Any]) -> list[str]:
    paths_config = config.get("paths", {})
    meme_config = config.get("meme", {})
    meme_dir = project_path(paths_config.get("meme_dir", "meme"))

    metadata_value = meme_config.get("metadata_path")
    image_dir_value = meme_config.get("image_dir")

    metadata_path = project_path(metadata_value) if metadata_value else meme_dir / "memes.json"
    image_dir = project_path(image_dir_value) if image_dir_value else meme_dir / "data"

    created: list[str] = []
    image_dir.mkdir(parents=True, exist_ok=True)
    created.append(str(image_dir))
    if write_if_missing(metadata_path, "{}\n"):
        created.append(str(metadata_path))
    return created


def bootstrap(config_path: str | Path = "agent.config.md") -> list[str]:
    config = load_config(config_path)
    created: list[str] = []

    for key in ("memory_dir", "db_dir", "skills_dir", "tools_dir"):
        directory = project_path(config["paths"][key])
        directory.mkdir(parents=True, exist_ok=True)
        created.append(str(directory))

    for item in config["memory"]["markdown_files"]:
        path = project_path(item["path"])
        if write_if_missing(path, render_markdown_memory(item)):
            created.append(str(path))

    schema_path = project_path(config["paths"]["schema"])
    ensure_parent(schema_path)
    schema_path.write_text(build_schema(config), encoding="utf-8")
    created.append(str(schema_path))

    database_path = project_path(config["paths"]["database"])
    ensure_parent(database_path)
    with sqlite3.connect(database_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    created.append(str(database_path))

    for skill in config.get("skills", []):
        path = project_path(skill["path"])
        if write_if_missing(path, render_skill(skill)):
            created.append(str(path))

    created.extend(bootstrap_meme_storage(config))

    return created


if __name__ == "__main__":
    for item in bootstrap():
        print(item)
