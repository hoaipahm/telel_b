"""Fail-closed Telegram authorization guard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardResult:
    """Authorization verdict for an incoming Telegram update."""

    allowed: bool
    reason: str


def check_telegram_access(
    user_id: int | None,
    chat_type: str | None,
    allowed_user_ids: set[int],
    *,
    allow_groups: bool = False,
) -> GuardResult:
    """Enforce fail-closed single-owner authorization on Telegram updates."""
    if not allowed_user_ids:
        return GuardResult(
            allowed=False,
            reason="not_configured: ALLOWED_TELEGRAM_USER_IDS is empty (fail-closed).",
        )
    if user_id is None:
        return GuardResult(allowed=False, reason="missing_user_id")
    if not allow_groups and chat_type != "private":
        return GuardResult(allowed=False, reason=f"non_private_chat:{chat_type}")
    if user_id not in allowed_user_ids:
        return GuardResult(allowed=False, reason=f"unauthorized_user:{user_id}")
    return GuardResult(allowed=True, reason="ok")
