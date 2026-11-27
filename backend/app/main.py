"""FastAPI application factory, reminder scheduler, and lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import AppServices, build_router, get_services_placeholder
from app.bot.telegram_app import BotManager
from app.config import Settings
from app.db.database import Database
from app.db.repositories import Repository
from app.llm.router import LLMRouter
from app.modules.brain import SecondBrainService
from app.modules.chat import ChatService
from app.modules.digest import DigestService
from app.modules.finance import FinanceService
from app.modules.remote import RemoteService
from app.security.auth import AdminAuth
from app.security.crypto import SecretVault


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI control plane and Telegram bot runtime."""
    settings = custom_settings or Settings()
    db = Database(settings.db_path)
    vault = SecretVault.from_env_or_file(settings.bot_master_key, settings.master_key_path)
    auth = AdminAuth.from_env_or_file(settings.web_admin_token, settings.admin_token_path)
    repo = Repository(db, vault)
    llm_router = LLMRouter(repo, settings)

    brain_svc = SecondBrainService(repo, timezone=settings.timezone)
    finance_svc = FinanceService(repo, llm_router)
    chat_svc = ChatService(
        repo,
        llm_router,
        timezone=settings.timezone,
        brain_svc=brain_svc,
        finance_svc=finance_svc,
    )
    digest_svc = DigestService(repo, llm_router)
    remote_svc = RemoteService(repo)
    bot_mgr = BotManager(
        settings=settings,
        repo=repo,
        chat_svc=chat_svc,
        brain_svc=brain_svc,
        finance_svc=finance_svc,
        digest_svc=digest_svc,
        remote_svc=remote_svc,
    )

    services = AppServices(
        settings=settings,
        auth=auth,
        repo=repo,
        bot=bot_mgr,
        chat=chat_svc,
        llm_router=llm_router,
        brain=brain_svc,
        finance=finance_svc,
        digest=digest_svc,
        remote=remote_svc,
    )

    scheduler = AsyncIOScheduler(timezone=UTC)

    async def dispatch_due_reminders() -> None:
        now_iso = datetime.now(UTC).isoformat()
        due = await repo.get_due_reminders(now_iso)
        for item in due:
            sent = await bot_mgr.send_proactive_message(
                int(item["chat_id"]), f"Nhắc việc: {item['message']}"
            )
            if sent:
                await repo.mark_reminder_status(int(item["id"]), "sent")

        # Optional daily morning RSS briefing
        briefing: dict[str, object] = await repo.get_setting("briefing", {})
        modules: dict[str, bool] = await repo.get_setting("modules", {})
        if not briefing.get("enabled") or not modules.get("digest") or not bot_mgr.running:
            return
        now_local = datetime.now(ZoneInfo(settings.timezone))
        today_str = now_local.strftime("%Y-%m-%d")
        target_hhmm = str(briefing.get("time_hhmm") or "07:30")
        if str(briefing.get("last_sent_date") or "") == today_str:
            return
        if now_local.strftime("%H:%M") < target_hhmm:
            return

        digest_text = await digest_svc.build_morning_briefing()
        if not digest_text:
            return
        allowed_ids = await bot_mgr.get_allowed_ids()
        sent_any = False
        for uid in sorted(allowed_ids):
            if await bot_mgr.send_proactive_message(uid, digest_text):
                sent_any = True
        if sent_any:
            updated = dict(briefing)
            updated["last_sent_date"] = today_str
            await repo.set_setting("briefing", updated)
            await repo.log_audit("system", "daily_briefing", "sent", today_str)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await db.initialize()
        await bot_mgr.start()
        scheduler.add_job(dispatch_due_reminders, "interval", seconds=20, id="reminders")
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            await bot_mgr.stop()
            await llm_router.close()

    app = FastAPI(
        title="TeleMind Personal Hub API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(HTTPException)
    async def http_exc_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    app.dependency_overrides[get_services_placeholder] = lambda: services
    app.include_router(build_router())
    return app
