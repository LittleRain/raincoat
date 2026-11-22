import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.mp4', '.mov', '.m4v', '.mkv', '.avi', '.webm'}


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, data=None, media_root=None):
        self.cache_lock = threading.RLock()
        self.data = Path(data or os.getenv('FAS_DATA_DIR', BASE / 'data')).resolve()
        self.root = Path(media_root or os.getenv('FAS_MEDIA_ROOT', self.data / 'media')).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.data / 'uploads').mkdir(exist_ok=True)
        (self.data / 'derived').mkdir(exist_ok=True)
        self.db = self.data / 'studio.sqlite3'
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('数据库版本较新，请升级应用')
            if version == 0:
                conn.executescript((BASE / 'backend/schema.sql').read_text())
            if version == 1:
                backup_dir = self.data / 'backups'
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f'pre-v2-{uuid4().hex}.sqlite3'
                with sqlite3.connect(backup_path) as backup:
                    conn.backup(backup)
            if version < 2:
                from .review import init_schema
                conn.execute('BEGIN IMMEDIATE')
                columns = {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
                if 'payload_json' not in columns:
                    conn.execute("ALTER TABLE jobs ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")
                init_schema(conn)
                conn.execute('PRAGMA user_version=2')
            session_columns = {row[1] for row in conn.execute('PRAGMA table_info(sessions)')}
            if 'sport' not in session_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN sport TEXT NOT NULL DEFAULT 'football'")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, sql, args=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    def session(self, sid):
        rows = self.rows('SELECT * FROM sessions WHERE id=? AND deleted=0', (sid,))
        return rows[0] if rows else None

    def register(self, sid, path, name, source, managed=False):
        mid, jid, stamp = uuid4().hex, uuid4().hex, now()
        with self.connect() as conn:
            # Recheck inside the transaction: a long upload can outlive its session.
            if not conn.execute('SELECT id FROM sessions WHERE id=? AND deleted=0', (sid,)).fetchone():
                raise ValueError('场次不存在')
            conn.execute('INSERT INTO media(id,session_id,name,source,path,managed,created_at) VALUES(?,?,?,?,?,?,?)',
                         (mid, sid, name, source, str(path), int(managed), stamp))
            conn.execute('INSERT INTO jobs(id,media_id,created_at,updated_at) VALUES(?,?,?,?)',
                         (jid, mid, stamp, stamp))
        return {'media_id': mid, 'job_id': jid}

    def approved_path(self, raw):
        path = Path(raw).expanduser().resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('路径必须位于已批准的媒体根目录内（不允许符号链接越界）')
        if not path.exists() or not (path.is_file() or path.is_dir()):
            raise ValueError('路径不存在或不是普通文件/目录')
        return path
