"""Parameterized async repositories for TeleMind Personal Hub."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.db.database import Database, utc_now_iso
from app.security.crypto import SecretVault, mask_secret


def _sanitize_fts_query(raw: str) -> str:
    tokens = re.findall(r"[\w]+", raw, flags=re.UNICODE)
    if not tokens:
        return ""
    return " AND ".join(f'"{tok}"*' for tok in tokens[:8])


class Repository:
    """Data access layer using strictly parameterized queries."""

    def __init__(self, db: Database, vault: SecretVault) -> None:
        self._db = db
        self._vault = vault

    # --- Settings & Secrets ---
    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "SELECT value_json FROM settings WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            if row is None:
                return default
            return json.loads(str(row["value_json"]))

    async def set_setting(self, key: str, value: Any) -> None:
        now = utc_now_iso()
        payload = json.dumps(value, ensure_ascii=False)
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, payload, now),
            )
            await conn.commit()

    async def set_secret(self, provider: str, plaintext: str) -> str:
        clean = plaintext.strip()
        now = utc_now_iso()
        async with self._db.connect() as conn:
            if not clean:
                await conn.execute("DELETE FROM secrets WHERE provider = ?", (provider,))
                await conn.commit()
                return ""
            encrypted = self._vault.encrypt(clean)
            hint = mask_secret(clean)
            await conn.execute(
                """
                INSERT INTO secrets (provider, encrypted_value, hint, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    encrypted_value = excluded.encrypted_value,
                    hint = excluded.hint,
                    updated_at = excluded.updated_at
                """,
                (provider, encrypted, hint, now),
            )
            await conn.commit()
            return hint

    async def get_secret(self, provider: str, env_fallback: str = "") -> str:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "SELECT encrypted_value FROM secrets WHERE provider = ?",
                (provider,),
            )
            row = await cursor.fetchone()
            if row is not None:
                return self._vault.decrypt(str(row["encrypted_value"]))
        return env_fallback.strip()

    async def list_secret_hints(self, env_fallbacks: dict[str, str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        async with self._db.connect() as conn:
            cursor = await conn.execute("SELECT provider, hint, updated_at FROM secrets")
            rows = {str(r["provider"]): dict(r) for r in await cursor.fetchall()}
        for provider in ("telegram", "gemini", "openai"):
            if provider in rows:
                result[provider] = {
                    "configured": True,
                    "source": "vault",
                    "hint": rows[provider]["hint"],
                    "updated_at": rows[provider]["updated_at"],
                }
            elif env_fallbacks.get(provider, "").strip():
                result[provider] = {
                    "configured": True,
                    "source": "env",
                    "hint": mask_secret(env_fallbacks[provider]),
                    "updated_at": None,
                }
            else:
                result[provider] = {
                    "configured": False,
                    "source": "none",
                    "hint": "",
                    "updated_at": None,
                }
        return result

    # --- Conversations ---
    async def add_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        tokens_used: int = 0,
    ) -> int:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO conversations (
                    chat_id, role, content, provider, model, tokens_used, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, role, content, provider, model, max(0, tokens_used), now),
            )
            await conn.commit()
            return int(cursor.lastrowid or 0)

    async def get_recent_messages(self, chat_id: int, limit: int = 12) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, chat_id, role, content, provider, model, tokens_used, created_at
                FROM conversations
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, safe_limit),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
        rows.reverse()
        return rows

    async def list_conversations(
        self, limit: int = 50, chat_id: int | None = None
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        async with self._db.connect() as conn:
            if chat_id is not None:
                cursor = await conn.execute(
                    """
                    SELECT id, chat_id, role, content, provider, model, tokens_used, created_at
                    FROM conversations
                    WHERE chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (chat_id, safe_limit),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT id, chat_id, role, content, provider, model, tokens_used, created_at
                    FROM conversations
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
            return [dict(r) for r in await cursor.fetchall()]

    async def clear_chat_history(self, chat_id: int) -> int:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
            await conn.commit()
            return int(cursor.rowcount)

    async def delete_conversation_message(self, msg_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM conversations WHERE id = ?", (msg_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def clear_all_conversations(self) -> int:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM conversations")
            await conn.commit()
            return int(cursor.rowcount)

    # --- Notes (Second Brain) ---
    async def create_note(
        self,
        title: str,
        content: str,
        tags: str = "",
        source_url: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO notes (title, content, tags, source_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title.strip(), content.strip(), tags.strip(), source_url, now, now),
            )
            await conn.commit()
            note_id = int(cursor.lastrowid or 0)
            row = await (
                await conn.execute(
                    """
                    SELECT id, title, content, tags, source_url, created_at, updated_at
                    FROM notes WHERE id = ?
                    """,
                    (note_id,),
                )
            ).fetchone()
            return dict(row) if row else {}

    async def search_notes(self, query: str = "", limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        clean_q = query.strip()
        async with self._db.connect() as conn:
            if not clean_q:
                cursor = await conn.execute(
                    """
                    SELECT id, title, content, tags, source_url, created_at, updated_at
                    FROM notes
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
                return [dict(r) for r in await cursor.fetchall()]

            fts_q = _sanitize_fts_query(clean_q)
            if fts_q:
                cursor = await conn.execute(
                    """
                    SELECT n.id, n.title, n.content, n.tags,
                           n.source_url, n.created_at, n.updated_at
                    FROM notes_fts f
                    JOIN notes n ON n.id = f.rowid
                    WHERE notes_fts MATCH ?
                    ORDER BY bm25(notes_fts), n.id DESC
                    LIMIT ?
                    """,
                    (fts_q, safe_limit),
                )
                rows = [dict(r) for r in await cursor.fetchall()]
                if rows:
                    return rows

            like_q = f"%{clean_q}%"
            cursor = await conn.execute(
                """
                SELECT id, title, content, tags, source_url, created_at, updated_at
                FROM notes
                WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like_q, like_q, like_q, safe_limit),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def update_note(
        self,
        note_id: int,
        title: str,
        content: str,
        tags: str = "",
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                UPDATE notes
                SET title = ?, content = ?, tags = ?, updated_at = ?
                WHERE id = ?
                """,
                (title.strip(), content.strip(), tags.strip(), now, note_id),
            )
            await conn.commit()
            if cursor.rowcount <= 0:
                return None
            row = await (
                await conn.execute(
                    """
                    SELECT id, title, content, tags, source_url, created_at, updated_at
                    FROM notes WHERE id = ?
                    """,
                    (note_id,),
                )
            ).fetchone()
            return dict(row) if row else None

    async def delete_note(self, note_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Reminders ---
    async def create_reminder(
        self, chat_id: int, message: str, remind_at_iso: str
    ) -> dict[str, Any]:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO reminders (chat_id, message, remind_at, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (chat_id, message.strip(), remind_at_iso, now),
            )
            await conn.commit()
            rid = int(cursor.lastrowid or 0)
            row = await (
                await conn.execute(
                    """
                    SELECT id, chat_id, message, remind_at, status, created_at
                    FROM reminders WHERE id = ?
                    """,
                    (rid,),
                )
            ).fetchone()
            return dict(row) if row else {}

    async def list_reminders(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        async with self._db.connect() as conn:
            if status:
                cursor = await conn.execute(
                    """
                    SELECT id, chat_id, message, remind_at, status, created_at
                    FROM reminders
                    WHERE status = ?
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (status, safe_limit),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT id, chat_id, message, remind_at, status, created_at
                    FROM reminders
                    ORDER BY remind_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
            return [dict(r) for r in await cursor.fetchall()]

    async def get_due_reminders(self, now_iso: str) -> list[dict[str, Any]]:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, chat_id, message, remind_at, status, created_at
                FROM reminders
                WHERE status = 'pending' AND remind_at <= ?
                ORDER BY remind_at ASC
                """,
                (now_iso,),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def mark_reminder_status(self, reminder_id: int, status: str) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "UPDATE reminders SET status = ? WHERE id = ?",
                (status, reminder_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_reminder(self, reminder_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Finance Transactions ---
    async def add_transaction(
        self,
        kind: str,
        amount_minor: int,
        category: str,
        note: str = "",
        currency: str = "VND",
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        occ = occurred_at or now
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO transactions (
                    kind, amount_minor, currency, category, note, occurred_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (kind, amount_minor, currency.upper(), category.strip(), note.strip(), occ, now),
            )
            await conn.commit()
            tid = int(cursor.lastrowid or 0)
            row = await (
                await conn.execute(
                    """
                    SELECT id, kind, amount_minor, currency, category, note, occurred_at, created_at
                    FROM transactions WHERE id = ?
                    """,
                    (tid,),
                )
            ).fetchone()
            return dict(row) if row else {}

    async def list_transactions(
        self, month_prefix: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        async with self._db.connect() as conn:
            if month_prefix:
                cursor = await conn.execute(
                    """
                    SELECT id, kind, amount_minor, currency, category, note, occurred_at, created_at
                    FROM transactions
                    WHERE substr(occurred_at, 1, 7) = ?
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT ?
                    """,
                    (month_prefix, safe_limit),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT id, kind, amount_minor, currency, category, note, occurred_at, created_at
                    FROM transactions
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
            return [dict(r) for r in await cursor.fetchall()]

    async def finance_summary(self, month_prefix: str) -> dict[str, Any]:
        async with self._db.connect() as conn:
            totals_cur = await conn.execute(
                """
                SELECT kind, currency, COALESCE(SUM(amount_minor), 0) AS total_minor
                FROM transactions
                WHERE substr(occurred_at, 1, 7) = ?
                GROUP BY kind, currency
                """,
                (month_prefix,),
            )
            totals = [dict(r) for r in await totals_cur.fetchall()]

            cat_cur = await conn.execute(
                """
                SELECT kind, category, currency,
                       COALESCE(SUM(amount_minor), 0) AS total_minor,
                       COUNT(*) AS tx_count
                FROM transactions
                WHERE substr(occurred_at, 1, 7) = ?
                GROUP BY kind, category, currency
                ORDER BY total_minor DESC
                """,
                (month_prefix,),
            )
            by_category = [dict(r) for r in await cat_cur.fetchall()]
        return {"month": month_prefix, "totals": totals, "by_category": by_category}

    async def update_transaction(
        self,
        tx_id: int,
        kind: str,
        amount_minor: int,
        currency: str,
        category: str,
        note: str = "",
    ) -> dict[str, Any] | None:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                UPDATE transactions
                SET kind = ?, amount_minor = ?, currency = ?, category = ?, note = ?
                WHERE id = ?
                """,
                (kind, amount_minor, currency.upper(), category.strip(), note.strip(), tx_id),
            )
            await conn.commit()
            if cursor.rowcount <= 0:
                return None
            row = await (
                await conn.execute(
                    """
                    SELECT id, kind, amount_minor, currency, category, note, occurred_at, created_at
                    FROM transactions WHERE id = ?
                    """,
                    (tx_id,),
                )
            ).fetchone()
            return dict(row) if row else None

    async def delete_transaction(self, tx_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Digests & Feeds ---
    async def save_digest(self, url: str, title: str, summary: str) -> dict[str, Any]:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "INSERT INTO digests (url, title, summary, created_at) VALUES (?, ?, ?, ?)",
                (url, title.strip(), summary.strip(), now),
            )
            await conn.commit()
            did = int(cursor.lastrowid or 0)
            row = await (
                await conn.execute(
                    "SELECT id, url, title, summary, created_at FROM digests WHERE id = ?",
                    (did,),
                )
            ).fetchone()
            return dict(row) if row else {}

    async def list_digests(self, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "SELECT id, url, title, summary, created_at FROM digests ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def delete_digest(self, digest_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM digests WHERE id = ?", (digest_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def add_feed(self, url: str, title: str) -> dict[str, Any]:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO feeds (url, title, enabled, created_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(url) DO UPDATE SET title = excluded.title, enabled = 1
                """,
                (url, title.strip(), now),
            )
            await conn.commit()
            row = await (
                await conn.execute(
                    """
                    SELECT id, url, title, enabled, last_checked_at, created_at
                    FROM feeds WHERE url = ?
                    """,
                    (url,),
                )
            ).fetchone()
            return dict(row) if row else {}

    async def get_feed(self, feed_id: int) -> dict[str, Any] | None:
        async with self._db.connect() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT id, url, title, enabled, last_checked_at, created_at
                    FROM feeds WHERE id = ?
                    """,
                    (feed_id,),
                )
            ).fetchone()
            return dict(row) if row else None

    async def update_feed(self, feed_id: int, title: str, enabled: bool) -> dict[str, Any] | None:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "UPDATE feeds SET title = ?, enabled = ? WHERE id = ?",
                (title.strip(), 1 if enabled else 0, feed_id),
            )
            await conn.commit()
            if cursor.rowcount <= 0:
                return None
        return await self.get_feed(feed_id)

    async def list_feeds(self) -> list[dict[str, Any]]:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, url, title, enabled, last_checked_at, created_at
                FROM feeds ORDER BY id DESC
                """
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def delete_feed(self, feed_id: int) -> bool:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Audit & LLM Usage ---
    async def log_audit(self, actor: str, action: str, status: str, detail: str = "") -> None:
        now = utc_now_iso()
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (actor, action, status, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (actor, action, status, detail[:500], now),
            )
            await conn.commit()

    async def list_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, actor, action, status, detail, created_at
                FROM audit_logs ORDER BY id DESC LIMIT ?
                """,
                (safe_limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def clear_audit_logs(self) -> int:
        async with self._db.connect() as conn:
            cursor = await conn.execute("DELETE FROM audit_logs")
            await conn.commit()
            return int(cursor.rowcount)

    async def log_usage(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        now = datetime.now(UTC)
        day_utc = now.strftime("%Y-%m-%d")
        async with self._db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO usage_logs (
                    provider, model, input_tokens, output_tokens, day_utc, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    model,
                    max(0, input_tokens),
                    max(0, output_tokens),
                    day_utc,
                    now.isoformat(),
                ),
            )
            await conn.commit()

    async def get_daily_usage(self, day_utc: str | None = None) -> dict[str, int]:
        target_day = day_utc or datetime.now(UTC).strftime("%Y-%m-%d")
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) AS requests,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM usage_logs
                WHERE day_utc = ?
                """,
                (target_day,),
            )
            row = await cursor.fetchone()
        if row is None:
            return {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        inp = int(row["input_tokens"])
        out = int(row["output_tokens"])
        return {
            "requests": int(row["requests"]),
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
        }
