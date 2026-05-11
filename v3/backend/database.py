import sqlite3
import os
from contextlib import contextmanager
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db_session():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def ensure_tables():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db_session() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                institution TEXT,
                degree TEXT,
                education TEXT,
                work_experience TEXT,
                skills TEXT,
                github_username TEXT,
                github_url TEXT,
                research_field TEXT,
                source TEXT,
                match_confidence TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'active',
                paper_id INTEGER,
                source_file TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS task_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                started_at TEXT,
                finished_at TEXT,
                uploaded_by TEXT
            );
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                file_path TEXT,
                team TEXT,
                raw_data TEXT,
                upload_time TEXT DEFAULT (datetime('now','localtime')),
                uploaded_by TEXT
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                author TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        # Ensure all columns exist on existing tables (safe ALTER — runs BEFORE indexes)
        for col, typ in [
            ("degree", "TEXT"), ("phone", "TEXT"), ("paper_id", "INTEGER"),
            ("source_file", "TEXT"), ("tags", "TEXT"), ("summary", "TEXT"),
            ("uploaded_by", "TEXT"), ("batch_name", "TEXT"), ("raw_data", "TEXT"),
        ]:
            try: conn.execute(f"ALTER TABLE candidates ADD COLUMN {col} {typ}")
            except: pass
        for col, typ in [("raw_data", "TEXT"), ("uploaded_by", "TEXT"), ("batch_name", "TEXT")]:
            try: conn.execute(f"ALTER TABLE papers ADD COLUMN {col} {typ}")
            except: pass
        for col, typ in [("batch_name", "TEXT")]:
            try: conn.execute(f"ALTER TABLE task_queue ADD COLUMN {col} {typ}")
            except: pass
        # Indexes (after columns exist)
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_c_email ON candidates(email)",
            "CREATE INDEX IF NOT EXISTS idx_c_name ON candidates(name)",
            "CREATE INDEX IF NOT EXISTS idx_c_phone ON candidates(phone)",
            "CREATE INDEX IF NOT EXISTS idx_c_source ON candidates(source)",
            "CREATE INDEX IF NOT EXISTS idx_c_degree ON candidates(degree)",
            "CREATE INDEX IF NOT EXISTS idx_c_github ON candidates(github_username)",
            "CREATE INDEX IF NOT EXISTS idx_t_status ON task_queue(status)",
            "CREATE INDEX IF NOT EXISTS idx_p_title ON papers(title)",
        ]:
            try: conn.execute(idx)
            except: pass
