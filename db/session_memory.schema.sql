PRAGMA foreign_keys = ON;


CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  title TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  metadata_json TEXT
);


CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);


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


CREATE TABLE IF NOT EXISTS web_crawls (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  query TEXT NOT NULL,
  result TEXT NOT NULL,
  ok INTEGER NOT NULL DEFAULT 1,
  error TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS reminders (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  message TEXT NOT NULL,
  recurrence TEXT NOT NULL DEFAULT 'once',
  timezone TEXT NOT NULL,
  run_at TEXT,
  time_of_day TEXT,
  day_of_week INTEGER,
  next_run_at TEXT,
  target_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_run_at TEXT,
  metadata_json TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS reminder_runs (
  id TEXT PRIMARY KEY,
  reminder_id TEXT NOT NULL,
  run_at TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_messages_session_created
ON messages(session_id, created_at);


CREATE INDEX IF NOT EXISTS idx_memory_events_type_status
ON memory_events(memory_type, status);


CREATE INDEX IF NOT EXISTS idx_reminders_status_next_run
ON reminders(status, next_run_at);


CREATE INDEX IF NOT EXISTS idx_reminder_runs_reminder_created
ON reminder_runs(reminder_id, created_at);


CREATE INDEX IF NOT EXISTS idx_web_crawls_created
ON web_crawls(created_at);


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
