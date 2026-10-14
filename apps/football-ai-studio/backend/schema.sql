CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, date TEXT NOT NULL,
 created_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS media (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 name TEXT NOT NULL, source TEXT NOT NULL, path TEXT NOT NULL,
 managed INTEGER NOT NULL, duration REAL, fps REAL, width INTEGER, height INTEGER,
 created_at TEXT NOT NULL, proxy_path TEXT, thumbnail_path TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
 type TEXT NOT NULL DEFAULT 'preprocess', status TEXT NOT NULL DEFAULT 'queued',
 stage TEXT NOT NULL DEFAULT '等待', progress REAL NOT NULL DEFAULT 0,
 error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS media_session ON media(session_id);
PRAGMA user_version = 1;
