"""Authenticated Control Plane REST endpoints with uniform error shape."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.bot.telegram_app import BotManager
from app.config import Settings
from app.db.repositories import Repository
from app.llm.base import BudgetExceededError, LLMError, ProviderNotConfiguredError
from app.llm.router import LLMRouter
from app.modules.brain import SecondBrainService
from app.modules.chat import ChatService
from app.modules.digest import DigestService
from app.modules.finance import FinanceService, parse_amount_to_integer
from app.modules.remote import RemoteService
from app.security.auth import AdminAuth
from app.security.ssrf import UnsafeURLError


@dataclass
class AppServices:
    """Shared service container bound to FastAPI app state."""

    settings: Settings
    auth: AdminAuth
    repo: Repository
    bot: BotManager
    chat: ChatService
    llm_router: LLMRouter
    brain: SecondBrainService
    finance: FinanceService
    digest: DigestService
    remote: RemoteService


def get_services_placeholder() -> AppServices:
    """Overridden on FastAPI app initialization."""
    raise RuntimeError("Services dependency not initialized.")


ServicesDep = Annotated[AppServices, Depends(get_services_placeholder)]


def require_admin(
    services: ServicesDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AppServices:
    """Enforce constant-time bearer token check on every /api/v1 route."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not services.auth.verify(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or missing bearer token."},
        )
    return services


AdminDep = Annotated[AppServices, Depends(require_admin)]


class ModulesUpdate(BaseModel):
    chat: bool
    brain: bool
    finance: bool
    digest: bool
    remote: bool


class AIConfigUpdate(BaseModel):
    primary_provider: str = Field(pattern="^(gemini|openai)$")
    fallback_enabled: bool = True
    gemini_model: str = Field(min_length=2, max_length=100)
    openai_model: str = Field(min_length=2, max_length=100)
    openai_base_url: str = Field(min_length=8, max_length=300)
    active_persona: str = Field(min_length=1, max_length=60)
    daily_request_cap: int = Field(ge=1, le=100000)
    daily_token_cap: int = Field(ge=1000, le=50000000)


class ThemeUpdate(BaseModel):
    mode: str = Field(pattern="^(system|light|dark)$")
    preset: str = Field(min_length=1, max_length=40)
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    foreground: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    fontFamily: str = Field(pattern="^(sans|mono|system)$")
    radius: str = Field(pattern="^(sm|md|lg)$")
    language: str = Field(pattern="^(vi|en)$")


class SecretUpdate(BaseModel):
    value: str = Field(max_length=500)


class AllowlistUpdate(BaseModel):
    user_ids: list[int]


class PersonasUpdate(BaseModel):
    personas: dict[str, str]


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    tags: str = Field(default="", max_length=200)


class ReminderCreate(BaseModel):
    chat_id: int
    raw: str = Field(min_length=3, max_length=400)


class TransactionCreate(BaseModel):
    kind: str = Field(pattern="^(expense|income)$")
    amount: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=200)


class DigestCreate(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class FeedCreate(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    title: str = Field(default="", max_length=150)


class FeedUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    enabled: bool = True


class ChatSend(BaseModel):
    chat_id: int = Field(default=0)
    message: str = Field(min_length=1, max_length=8000)


class AITestRequest(BaseModel):
    provider: str = Field(pattern="^(gemini|openai)$")


class BriefingUpdate(BaseModel):
    enabled: bool
    time_hhmm: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    last_sent_date: str = Field(default="")


def _parse_amount_input(raw_amount: str) -> tuple[int, str]:
    """Parse human-entered amount strings like '55k' or '12.50 USD' cleanly."""
    clean = raw_amount.strip()
    parts = clean.split()
    num = parts[0] if parts else ""
    unit = parts[1] if len(parts) > 1 else ""
    matched = re.match(r"^(\d+(?:[.,]\d+)?)\s*([a-zA-ZđĐ]+)?$", clean)
    if matched:
        num, unit = matched.group(1), matched.group(2) or ""
    return parse_amount_to_integer(num, unit)


MonthQuery = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]


def build_router() -> APIRouter:
    """Create API router with health probes and authenticated v1 endpoints."""
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready(services: ServicesDep) -> dict[str, Any]:
        usage = await services.repo.get_daily_usage()
        return {
            "status": "ready",
            "bot_running": services.bot.running,
            "daily_requests": usage["requests"],
        }

    @router.get("/api/v1/overview")
    async def overview(services: AdminDep) -> dict[str, Any]:
        env_fallbacks = {
            "telegram": services.settings.telegram_bot_token,
            "gemini": services.settings.gemini_api_key,
            "openai": services.settings.openai_api_key,
        }
        secrets_meta = await services.repo.list_secret_hints(env_fallbacks)
        modules = await services.repo.get_setting("modules", {})
        ai_cfg = await services.repo.get_setting("ai", {})
        theme = await services.repo.get_setting("theme", {})
        personas = await services.repo.get_setting("personas", {})
        briefing = await services.repo.get_setting(
            "briefing", {"enabled": False, "time_hhmm": "07:30", "last_sent_date": ""}
        )
        usage = await services.repo.get_daily_usage()

        env_ids = services.settings.parsed_allowed_user_ids()
        db_ids = await services.repo.get_setting("allowed_telegram_user_ids", [])
        merged_ids = sorted(env_ids | {int(x) for x in db_ids if str(x).isdigit()})

        return {
            "bot": {
                "running": services.bot.running,
                "last_error": services.bot.last_error,
                "allowed_user_ids": merged_ids,
                "polling_disabled": services.settings.disable_bot_polling,
            },
            "secrets": secrets_meta,
            "modules": modules,
            "ai": ai_cfg,
            "theme": theme,
            "personas": personas,
            "briefing": briefing,
            "usage": usage,
        }

    @router.put("/api/v1/settings/modules")
    async def update_modules(payload: ModulesUpdate, services: AdminDep) -> dict[str, bool]:
        data = payload.model_dump()
        await services.repo.set_setting("modules", data)
        await services.repo.log_audit("web_admin", "update_modules", "ok", str(data))
        return data

    @router.put("/api/v1/settings/ai")
    async def update_ai(payload: AIConfigUpdate, services: AdminDep) -> dict[str, Any]:
        data = payload.model_dump()
        await services.repo.set_setting("ai", data)
        await services.repo.log_audit(
            "web_admin",
            "update_ai",
            "ok",
            f"primary={payload.primary_provider}",
        )
        return data

    @router.put("/api/v1/settings/theme")
    async def update_theme(payload: ThemeUpdate, services: AdminDep) -> dict[str, Any]:
        data = payload.model_dump()
        await services.repo.set_setting("theme", data)
        return data

    @router.put("/api/v1/settings/personas")
    async def update_personas(payload: PersonasUpdate, services: AdminDep) -> dict[str, str]:
        cleaned = {
            k.strip().lower(): v.strip()
            for k, v in payload.personas.items()
            if k.strip() and v.strip()
        }
        await services.repo.set_setting("personas", cleaned)
        return cleaned

    @router.put("/api/v1/settings/briefing")
    async def update_briefing(payload: BriefingUpdate, services: AdminDep) -> dict[str, Any]:
        existing = await services.repo.get_setting("briefing", {})
        data = {
            "enabled": payload.enabled,
            "time_hhmm": payload.time_hhmm,
            "last_sent_date": payload.last_sent_date or str(existing.get("last_sent_date") or ""),
        }
        await services.repo.set_setting("briefing", data)
        await services.repo.log_audit(
            "web_admin", "update_briefing", "ok", f"{data['enabled']}@{data['time_hhmm']}"
        )
        return data

    @router.post("/api/v1/digest/briefing/send")
    async def send_briefing_now(services: AdminDep) -> dict[str, Any]:
        text = await services.digest.build_morning_briefing()
        if not text:
            raise HTTPException(
                status_code=400,
                detail={"code": "NO_FEEDS", "message": "Chưa có nguồn RSS đang bật để gửi."},
            )
        if not services.bot.running:
            raise HTTPException(
                status_code=503,
                detail={"code": "BOT_OFFLINE", "message": "Telegram Bot hiện chưa chạy."},
            )
        allowed_ids = await services.bot.get_allowed_ids()
        if not allowed_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "NO_ALLOWLIST",
                    "message": "Chưa có Telegram User ID trong Allowlist.",
                },
            )
        sent = 0
        for uid in sorted(allowed_ids):
            if await services.bot.send_proactive_message(uid, text):
                sent += 1
        return {"sent_chats": sent, "preview": text}

    @router.put("/api/v1/settings/telegram-allowlist")
    async def update_allowlist(
        payload: AllowlistUpdate, services: AdminDep
    ) -> dict[str, list[int]]:
        unique = sorted({uid for uid in payload.user_ids if uid > 0})
        await services.repo.set_setting("allowed_telegram_user_ids", unique)
        await services.repo.log_audit("web_admin", "update_allowlist", "ok", f"count={len(unique)}")
        return {"user_ids": unique}

    @router.put("/api/v1/secrets/{provider}")
    async def update_secret(
        provider: str,
        payload: SecretUpdate,
        services: AdminDep,
    ) -> dict[str, Any]:
        if provider not in ("telegram", "gemini", "openai"):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PROVIDER", "message": "Unknown provider."},
            )
        hint = await services.repo.set_secret(provider, payload.value)
        status_note = "updated" if hint else "cleared"
        await services.repo.log_audit("web_admin", f"set_secret:{provider}", "ok", status_note)
        if provider == "telegram":
            await services.bot.reload()
        return {"provider": provider, "configured": bool(hint), "hint": hint}

    @router.delete("/api/v1/secrets/{provider}")
    async def delete_secret(provider: str, services: AdminDep) -> dict[str, Any]:
        if provider not in ("telegram", "gemini", "openai"):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_PROVIDER", "message": "Unknown provider."},
            )
        await services.repo.set_secret(provider, "")
        await services.repo.log_audit("web_admin", f"delete_secret:{provider}", "ok", "cleared")
        if provider == "telegram":
            await services.bot.reload()
        return {"provider": provider, "configured": False, "hint": ""}

    @router.post("/api/v1/ai/test")
    async def test_ai_provider(payload: AITestRequest, services: AdminDep) -> dict[str, Any]:
        result = await services.llm_router.test_provider(payload.provider)
        await services.repo.log_audit(
            "web_admin",
            f"test_provider:{payload.provider}",
            "ok" if result["ok"] else "error",
            result["error"][:200] if result["error"] else f"models={len(result['models'])}",
        )
        return result

    @router.post("/api/v1/bot/reload")
    async def reload_bot(services: AdminDep) -> dict[str, Any]:
        await services.bot.reload()
        return {"running": services.bot.running, "last_error": services.bot.last_error}

    @router.get("/api/v1/conversations")
    async def list_conversations(
        services: AdminDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, Any]:
        items = await services.repo.list_conversations(limit=limit)
        return {"items": items}

    @router.post("/api/v1/chat", status_code=201)
    async def desktop_chat(payload: ChatSend, services: AdminDep) -> dict[str, Any]:
        try:
            res = await services.chat.reply(payload.chat_id, payload.message)
        except (ProviderNotConfiguredError, BudgetExceededError, LLMError) as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "LLM_ERROR", "message": str(exc)},
            ) from exc
        return {
            "text": res.text,
            "provider": res.provider,
            "model": res.model,
            "input_tokens": res.input_tokens,
            "output_tokens": res.output_tokens,
        }

    @router.delete("/api/v1/conversations/{msg_id}")
    async def delete_conversation_message(msg_id: int, services: AdminDep) -> dict[str, bool]:
        ok = await services.repo.delete_conversation_message(msg_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Message not found."},
            )
        return {"deleted": True}

    @router.delete("/api/v1/conversations")
    async def clear_conversations(
        services: AdminDep,
        chat_id: Annotated[int | None, Query()] = None,
    ) -> dict[str, int]:
        count = (
            await services.repo.clear_chat_history(chat_id)
            if chat_id is not None
            else await services.repo.clear_all_conversations()
        )
        return {"deleted_count": count}

    @router.get("/api/v1/notes")
    async def list_notes(
        services: AdminDep,
        q: Annotated[str, Query(max_length=150)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        items = await services.repo.search_notes(query=q, limit=limit)
        return {"items": items}

    @router.post("/api/v1/notes", status_code=201)
    async def create_note(payload: NoteCreate, services: AdminDep) -> dict[str, Any]:
        return await services.repo.create_note(
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )

    @router.put("/api/v1/notes/{note_id}")
    async def update_note(
        note_id: int, payload: NoteCreate, services: AdminDep
    ) -> dict[str, Any]:
        updated = await services.repo.update_note(
            note_id=note_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Note not found."},
            )
        return updated

    @router.delete("/api/v1/notes/{note_id}")
    async def delete_note(note_id: int, services: AdminDep) -> dict[str, bool]:
        ok = await services.repo.delete_note(note_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Note not found."},
            )
        return {"deleted": True}

    @router.get("/api/v1/reminders")
    async def list_reminders(services: AdminDep) -> dict[str, Any]:
        return {"items": await services.repo.list_reminders()}

    @router.post("/api/v1/reminders", status_code=201)
    async def create_reminder(payload: ReminderCreate, services: AdminDep) -> dict[str, Any]:
        try:
            return await services.brain.schedule_reminder(payload.chat_id, payload.raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            ) from exc

    @router.delete("/api/v1/reminders/{reminder_id}")
    async def cancel_reminder(
        reminder_id: int,
        services: AdminDep,
        hard: bool = False,
    ) -> dict[str, bool]:
        if hard:
            ok = await services.repo.delete_reminder(reminder_id)
        else:
            ok = await services.repo.mark_reminder_status(reminder_id, "cancelled")
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Reminder not found."},
            )
        return {"deleted" if hard else "cancelled": True}

    @router.get("/api/v1/finance/transactions")
    async def list_transactions(
        services: AdminDep,
        month: MonthQuery = None,
    ) -> dict[str, Any]:
        items = await services.repo.list_transactions(month_prefix=month)
        return {"items": items}

    @router.post("/api/v1/finance/transactions", status_code=201)
    async def create_transaction(payload: TransactionCreate, services: AdminDep) -> dict[str, Any]:
        try:
            amount_minor, currency = _parse_amount_input(payload.amount)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_AMOUNT", "message": str(exc)},
            ) from exc

        return await services.repo.add_transaction(
            kind=payload.kind,
            amount_minor=amount_minor,
            currency=currency,
            category=payload.category,
            note=payload.note,
        )

    @router.put("/api/v1/finance/transactions/{tx_id}")
    async def update_transaction(
        tx_id: int, payload: TransactionCreate, services: AdminDep
    ) -> dict[str, Any]:
        try:
            amount_minor, currency = _parse_amount_input(payload.amount)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_AMOUNT", "message": str(exc)},
            ) from exc

        updated = await services.repo.update_transaction(
            tx_id=tx_id,
            kind=payload.kind,
            amount_minor=amount_minor,
            currency=currency,
            category=payload.category,
            note=payload.note,
        )
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Transaction not found."},
            )
        return updated

    @router.delete("/api/v1/finance/transactions/{tx_id}")
    async def delete_transaction(tx_id: int, services: AdminDep) -> dict[str, bool]:
        ok = await services.repo.delete_transaction(tx_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Transaction not found."},
            )
        return {"deleted": True}

    @router.get("/api/v1/finance/summary")
    async def finance_summary(services: AdminDep, month: MonthQuery = None) -> dict[str, Any]:
        return await services.finance.monthly_report(month)

    @router.get("/api/v1/finance/export.csv")
    async def export_finance_csv(services: AdminDep, month: MonthQuery = None) -> Response:
        csv_text = await services.finance.export_csv(month)
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="finance-export.csv"'},
        )

    @router.get("/api/v1/digest")
    async def list_digests(services: AdminDep) -> dict[str, Any]:
        return {"items": await services.repo.list_digests()}

    @router.post("/api/v1/digest", status_code=201)
    async def create_digest(payload: DigestCreate, services: AdminDep) -> dict[str, Any]:
        try:
            return await services.digest.summarize_url(payload.url)
        except UnsafeURLError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "UNSAFE_URL", "message": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "DIGEST_ERROR", "message": str(exc)},
            ) from exc

    @router.delete("/api/v1/digest/{digest_id}")
    async def delete_digest(digest_id: int, services: AdminDep) -> dict[str, bool]:
        ok = await services.repo.delete_digest(digest_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Digest not found."},
            )
        return {"deleted": True}

    @router.get("/api/v1/digest/feeds")
    async def list_feeds(services: AdminDep) -> dict[str, Any]:
        return {"items": await services.repo.list_feeds()}

    @router.post("/api/v1/digest/feeds", status_code=201)
    async def create_feed(payload: FeedCreate, services: AdminDep) -> dict[str, Any]:
        try:
            return await services.digest.subscribe_feed(payload.url, payload.title)
        except UnsafeURLError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "UNSAFE_URL", "message": str(exc)},
            ) from exc

    @router.put("/api/v1/digest/feeds/{feed_id}")
    async def update_feed(
        feed_id: int, payload: FeedUpdate, services: AdminDep
    ) -> dict[str, Any]:
        updated = await services.repo.update_feed(feed_id, payload.title, payload.enabled)
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Feed not found."},
            )
        return updated

    @router.get("/api/v1/digest/feeds/{feed_id}/items")
    async def fetch_feed_items(feed_id: int, services: AdminDep) -> dict[str, Any]:
        feed = await services.repo.get_feed(feed_id)
        if feed is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Feed not found."},
            )
        try:
            items = await services.digest.fetch_feed_headlines(str(feed["url"]), limit=8)
        except UnsafeURLError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "UNSAFE_URL", "message": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "FEED_ERROR", "message": str(exc)},
            ) from exc
        return {"items": items}

    @router.delete("/api/v1/digest/feeds/{feed_id}")
    async def delete_feed(feed_id: int, services: AdminDep) -> dict[str, bool]:
        ok = await services.repo.delete_feed(feed_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Feed not found."},
            )
        return {"deleted": True}

    @router.get("/api/v1/remote/status")
    async def remote_status(services: AdminDep) -> dict[str, Any]:
        modules = await services.repo.get_setting("modules", {})
        if not modules.get("remote", False):
            return {"enabled": False, "host": None, "containers": []}
        host = services.remote.get_host_stats()
        containers: list[dict[str, str]] = []
        docker_error = ""
        try:
            containers = await services.remote.list_docker_containers()
        except RuntimeError as exc:
            docker_error = str(exc)
        return {
            "enabled": True,
            "host": host,
            "containers": containers,
            "docker_error": docker_error,
        }

    @router.post("/api/v1/remote/docker/{container_name}/logs")
    async def remote_docker_logs(container_name: str, services: AdminDep) -> dict[str, str]:
        modules = await services.repo.get_setting("modules", {})
        if not modules.get("remote", False):
            raise HTTPException(
                status_code=403,
                detail={"code": "REMOTE_DISABLED", "message": "Module Remote đang tắt."},
            )
        try:
            logs = await services.remote.read_docker_logs(container_name, tail=40)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_CONTAINER", "message": str(exc)},
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "DOCKER_ERROR", "message": str(exc)},
            ) from exc
        await services.repo.log_audit("web_admin", "remote:docker_logs", "executed", container_name)
        return {"container": container_name, "logs": logs}

    @router.get("/api/v1/audit-logs")
    async def audit_logs(
        services: AdminDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, Any]:
        return {"items": await services.repo.list_audit_logs(limit=limit)}

    @router.delete("/api/v1/audit-logs")
    async def clear_audit_logs(services: AdminDep) -> dict[str, int]:
        count = await services.repo.clear_audit_logs()
        return {"deleted_count": count}

    return router
