"""Second Brain module: quick notes, FTS5 search, and scheduled Telegram reminders."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db.repositories import Repository

RELATIVE_RE = re.compile(r"^(\d+)\s*(m|min|mins|p|phut|phút|h|gio|giờ|d|ngay|ngày)\b\s*(.+)$", re.I)
TIME_TODAY_RE = re.compile(r"^(\d{1,2}):(\d{2})\b\s*(.+)$")
ISO_DT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{1,2}:\d{2})\b\s*(.+)$")


def parse_reminder_input(
    raw: str, tz_name: str = "Asia/Ho_Chi_Minh", now_utc: datetime | None = None
) -> tuple[datetime, str]:
    """Parse reminder expressions like '30m hop team' or '09:30 gui bao cao'."""
    text = raw.strip()
    if not text:
        raise ValueError("Nội dung nhắc nhở không được để trống.")

    tz = ZoneInfo(tz_name)
    base_utc = now_utc or datetime.now(UTC)
    local_now = base_utc.astimezone(tz)

    rel = RELATIVE_RE.match(text)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2).lower()
        msg = rel.group(3).strip()
        if amount <= 0 or not msg:
            raise ValueError("Thời gian hoặc nội dung nhắc nhở không hợp lệ.")
        if unit.startswith(("m", "p")):
            target = base_utc + timedelta(minutes=amount)
        elif unit.startswith(("h", "g")):
            target = base_utc + timedelta(hours=amount)
        else:
            target = base_utc + timedelta(days=amount)
        return target, msg

    iso_m = ISO_DT_RE.match(text)
    if iso_m:
        date_str, time_str, msg = iso_m.group(1), iso_m.group(2), iso_m.group(3).strip()
        dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        return dt_local.astimezone(UTC), msg

    hm = TIME_TODAY_RE.match(text)
    if hm:
        hour, minute, msg = int(hm.group(1)), int(hm.group(2)), hm.group(3).strip()
        if not (0 <= hour <= 23 and 0 <= minute <= 59) or not msg:
            raise ValueError("Giờ nhắc nhở không hợp lệ (00:00–23:59).")
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC), msg

    raise ValueError(
        "Cú pháp hỗ trợ: `30m Nội dung`, `2h Nội dung`, `1d Nội dung`, "
        "`09:30 Nội dung`, hoặc `2026-11-28 09:00 Nội dung`."
    )


def parse_note_input(raw: str) -> tuple[str, str, str]:
    """Parse note input formatted as 'Title | Content #tag1 #tag2' or free text."""
    text = raw.strip()
    if not text:
        raise ValueError("Nội dung ghi chú không được để trống.")
    tags = re.findall(r"#([\w-]+)", text, flags=re.UNICODE)
    cleaned = re.sub(r"#[\w-]+", "", text, flags=re.UNICODE).strip()

    if "|" in cleaned:
        title_part, body_part = cleaned.split("|", 1)
        title = title_part.strip() or "Ghi chú nhanh"
        content = body_part.strip() or title
    else:
        first_line = cleaned.splitlines()[0].strip()
        title = first_line[:80]
        content = cleaned
    return title, content, ", ".join(dict.fromkeys(tags))


class SecondBrainService:
    """Manages personal notes, search, and reminder scheduling."""

    def __init__(self, repo: Repository, timezone: str = "Asia/Ho_Chi_Minh") -> None:
        self._repo = repo
        self._tz = timezone

    async def add_note_from_text(self, raw: str, source_url: str | None = None) -> dict[str, Any]:
        title, content, tags = parse_note_input(raw)
        return await self._repo.create_note(
            title=title, content=content, tags=tags, source_url=source_url
        )

    async def find_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return await self._repo.search_notes(query=query, limit=limit)

    async def schedule_reminder(self, chat_id: int, raw: str) -> dict[str, Any]:
        target_utc, message = parse_reminder_input(raw, tz_name=self._tz)
        return await self._repo.create_reminder(
            chat_id=chat_id, message=message, remind_at_iso=target_utc.isoformat()
        )
