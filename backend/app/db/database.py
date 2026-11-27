"""Async SQLite database initialization, schema migrations, and connection helper."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets (
    provider TEXT PRIMARY KEY CHECK (provider IN ('telegram', 'gemini', 'openai')),
    encrypted_value TEXT NOT NULL,
    hint TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    tokens_used INTEGER NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_chat_created
    ON conversations (chat_id, id DESC);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_created
    ON notes (created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title,
    content,
    tags,
    content='notes',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
    VALUES ('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO notes_fts(rowid, title, content, tags)
    VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reminders_status_time
    ON reminders (status, remind_at);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('expense', 'income')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL DEFAULT 'VND',
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_occurred
    ON transactions (occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_category
    ON transactions (category, kind);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_digests_created
    ON digests (created_at DESC);

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_checked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created
    ON audit_logs (id DESC);

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    day_utc TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_day
    ON usage_logs (day_utc);
"""

DEFAULT_SETTINGS: dict[str, object] = {
    "modules": {
        "chat": True,
        "brain": True,
        "finance": True,
        "digest": True,
        "remote": False,
    },
    "ai": {
        "primary_provider": "gemini",
        "fallback_enabled": True,
        "gemini_model": "gemini-3.8-flash",
        "openai_model": "gpt-6-luna",
        "openai_base_url": "https://api.openai.com/v1",
        "active_persona": "assistant",
        "daily_request_cap": 200,
        "daily_token_cap": 500000,
    },
    "personas": {
        "assistant": (
            "Bạn là trợ lý cá nhân thông minh, súc tích và trung thực. "
            "Trả lời bằng ngôn ngữ người dùng sử dụng (ưu tiên tiếng Việt)."
        ),
        "coder": (
            "Bạn là Senior Software Engineer. Trả lời chính xác, code sạch, "
            "nhắc rõ rủi ro bảo mật và không bịa API."
        ),
        "translator": (
            "Bạn là dịch giả chuyên nghiệp Anh-Việt. Dịch tự nhiên, giữ nguyên thuật ngữ kỹ thuật."
        ),
        "analyst": (
            "Bạn là chuyên gia phân tích dữ liệu và tài chính cá nhân. "
            "Trả lời có số liệu và gạch đầu dòng rõ ràng."
        ),
    },
    "theme": {
        "mode": "dark",
        "preset": "matrix",
        "accent": "#22c55e",
        "background": "#040805",
        "foreground": "#ffffff",
        "fontFamily": "sans",
        "radius": "md",
        "language": "vi",
    },
    "briefing": {
        "enabled": False,
        "time_hhmm": "07:30",
        "last_sent_date": "",
    },
}


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


class Database:
    """Async SQLite manager supporting WAL mode, migrations, and safe transactions."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create database directory, apply schema, and seed default settings."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as conn:
            await conn.executescript(SCHEMA_SQL)
            now = utc_now_iso()
            for key, value in DEFAULT_SETTINGS.items():
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO settings (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
            await conn.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield an async SQLite connection configured with row factory and foreign keys."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA busy_timeout = 5000;")
        try:
            yield conn
        finally:
            await conn.close()
