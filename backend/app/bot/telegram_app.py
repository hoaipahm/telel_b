"""Telegram Bot handler layer with fail-closed allowlist and 2-step confirmations."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from collections.abc import Coroutine
from contextlib import suppress
from typing import Any, TypeVar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import Settings
from app.db.repositories import Repository
from app.llm.base import BudgetExceededError, LLMError, ProviderNotConfiguredError
from app.modules.brain import SecondBrainService
from app.modules.chat import ChatService
from app.modules.digest import DigestService
from app.modules.finance import FinanceService, format_amount
from app.modules.remote import RemoteService
from app.security.ssrf import UnsafeURLError
from app.security.telegram_guard import check_telegram_access

T = TypeVar("T")
logger = logging.getLogger(__name__)

MAX_TG_FILE_BYTES = 10 * 1024 * 1024


def chunk_telegram_text(text: str, max_len: int = 3900) -> list[str]:
    """Split long replies safely below Telegram's 4,096-character limit."""
    clean = text.strip()
    if not clean:
        return ["(Trống)"]
    if len(clean) <= max_len:
        return [clean]

    chunks: list[str] = []
    remaining = clean
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = remaining.rfind(" ", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def markdown_to_telegram_html(text: str) -> str:
    """Safely convert common Markdown formatting into valid Telegram HTML."""
    tokens: list[tuple[str, str]] = []

    def _stash(rendered_html: str) -> str:
        key = f"\x00TM{len(tokens)}\x00"
        tokens.append((key, rendered_html))
        return key

    work = text
    work = re.sub(
        r"```(?:\w+)?\n?([\s\S]*?)```",
        lambda m: _stash(f"<pre><code>{html.escape(m.group(1).strip(), quote=False)}</code></pre>"),
        work,
    )
    work = re.sub(
        r"`([^`\n]+)`",
        lambda m: _stash(f"<code>{html.escape(m.group(1), quote=False)}</code>"),
        work,
    )
    work = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: _stash(
            f'<a href="{html.escape(m.group(2), quote=True)}">'
            f"{html.escape(m.group(1), quote=False)}</a>"
        ),
        work,
    )

    escaped = html.escape(work, quote=False)
    escaped = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", escaped, flags=re.M)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)

    for key, rendered_html in reversed(tokens):
        escaped = escaped.replace(key, rendered_html)
    return escaped


class BotManager:
    """Manages Telegram polling lifecycle and command routing."""

    def __init__(
        self,
        *,
        settings: Settings,
        repo: Repository,
        chat_svc: ChatService,
        brain_svc: SecondBrainService,
        finance_svc: FinanceService,
        digest_svc: DigestService,
        remote_svc: RemoteService,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._chat = chat_svc
        self._brain = brain_svc
        self._finance = finance_svc
        self._digest = digest_svc
        self._remote = remote_svc
        self._app: Application[Any, Any, Any, Any, Any, Any] | None = None
        self.running = False
        self.last_error = ""

    async def get_allowed_ids(self) -> set[int]:
        env_ids = self._settings.parsed_allowed_user_ids()
        db_ids_raw = await self._repo.get_setting("allowed_telegram_user_ids", [])
        db_ids = (
            {int(x) for x in db_ids_raw if str(x).isdigit()}
            if isinstance(db_ids_raw, list)
            else set()
        )
        return env_ids | db_ids

    async def _authorize(self, update: Update) -> bool:
        user = update.effective_user
        chat = update.effective_chat
        allowed_ids = await self.get_allowed_ids()
        verdict = check_telegram_access(
            user.id if user else None,
            chat.type if chat else None,
            allowed_ids,
        )
        if not verdict.allowed:
            uid = user.id if user else "unknown"
            await self._repo.log_audit(f"tg:{uid}", "telegram_access", "denied", verdict.reason)
            if update.effective_message and chat and chat.type == "private":
                await update.effective_message.reply_text(
                    "Truy cập bị từ chối (Fail-Closed). "
                    "Hãy cấu hình Telegram User ID của bạn trong TeleMind Hub → Cài đặt chung."
                )
            elif update.callback_query:
                await update.callback_query.answer("Không có quyền thao tác.", show_alert=True)
            return False
        return True

    async def _is_module_enabled(self, module_name: str) -> bool:
        modules: dict[str, bool] = await self._repo.get_setting("modules", {})
        return bool(modules.get(module_name, False))

    async def _send_reply(self, update: Update, text: str) -> None:
        if not update.effective_message:
            return
        for part in chunk_telegram_text(text):
            try:
                await update.effective_message.reply_text(
                    markdown_to_telegram_html(part), parse_mode=ParseMode.HTML
                )
            except BadRequest:
                await update.effective_message.reply_text(part)

    async def _run_with_typing(
        self,
        chat_id: int,
        bot: Any,
        coro: Coroutine[Any, Any, T],
    ) -> T:
        """Keep native Telegram typing indicator alive while awaiting slow operations."""

        async def _pulse() -> None:
            while True:
                with suppress(Exception):
                    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4.0)

        pulse_task = asyncio.create_task(_pulse())
        try:
            return await coro
        finally:
            pulse_task.cancel()
            with suppress(asyncio.CancelledError):
                await pulse_task

    async def send_proactive_message(self, chat_id: int, text: str) -> bool:
        """Send scheduled reminders or alerts when bot application is active."""
        if not self._app or not self.running:
            return False
        for part in chunk_telegram_text(text):
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=markdown_to_telegram_html(part),
                    parse_mode=ParseMode.HTML,
                )
            except BadRequest:
                await self._app.bot.send_message(chat_id=chat_id, text=part)
        return True

    # --- Command Handlers ---
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        modules: dict[str, bool] = await self._repo.get_setting("modules", {})
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        provider_name = ai_cfg.get("primary_provider", "gemini")
        persona_name = ai_cfg.get("active_persona", "assistant")
        lines = [
            "TeleMind Personal Hub đã sẵn sàng.",
            f"AI chính: `{provider_name}` | Persona: `{persona_name}`",
            "",
            "Lệnh nhanh:",
            "• `/model gemini|openai` — Đổi AI provider",
            "• `/mode assistant|coder|translator|analyst` — Đổi nhân cách AI",
            "• `/clear` — Xóa lịch sử chat hiện tại",
            "• `/note Tiêu đề | Nội dung #tag` & `/find từ khóa` — Second Brain",
            "• `/remind 30m Nội dung` (hoặc `09:30 Nội dung`) — Hẹn giờ nhắc",
            "• `/chi 55k ăn trưa`, `/thu 15tr lương`, `/thongke` — Tài chính",
            "• `/tomtat https://...` & `/feed https://...` — Tóm tắt link/RSS",
            "• `/pc`, `/docker`, `/dockerlogs <tên>` — Giám sát máy (nếu bật Remote)",
            "",
            "Trạng thái module: "
            + ", ".join(f"{k}={'ON' if v else 'OFF'}" for k, v in modules.items()),
        ]
        await self._send_reply(update, "\n".join(lines))

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        arg = context.args[0].lower().strip() if context.args else ""
        if arg not in ("gemini", "openai"):
            cur_prov = ai_cfg.get("primary_provider", "gemini")
            await self._send_reply(
                update,
                f"Provider hiện tại: `{cur_prov}`. Dùng `/model gemini` hoặc `/model openai`.",
            )
            return
        ai_cfg["primary_provider"] = arg
        await self._repo.set_setting("ai", ai_cfg)
        await self._send_reply(update, f"Đã chuyển AI mặc định sang `{arg}`.")

    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        personas: dict[str, str] = await self._repo.get_setting("personas", {})
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        arg = context.args[0].lower().strip() if context.args else ""
        if not arg or arg not in personas:
            avail = ", ".join(personas.keys())
            cur_mode = ai_cfg.get("active_persona", "assistant")
            await self._send_reply(
                update,
                f"Persona hiện tại: `{cur_mode}`.\nCó sẵn: {avail}",
            )
            return
        ai_cfg["active_persona"] = arg
        await self._repo.set_setting("ai", ai_cfg)
        await self._send_reply(update, f"Đã chuyển sang chế độ `{arg}`.")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update) or not update.effective_chat:
            return
        count = await self._repo.clear_chat_history(update.effective_chat.id)
        await self._send_reply(update, f"Đã xóa {count} tin nhắn trong ngữ cảnh hội thoại này.")

    async def cmd_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("brain"):
            await self._send_reply(
                update, "Module Second Brain đang tắt. Hãy bật trong TeleMind Hub."
            )
            return
        raw = " ".join(context.args or []).strip()
        try:
            note = await self._brain.add_note_from_text(raw)
        except ValueError as exc:
            await self._send_reply(update, str(exc))
            return
        await self._send_reply(
            update, f"Đã lưu ghi chú #{note['id']}: {note['title']}\nTags: {note['tags'] or '-'}"
        )

    async def cmd_find(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("brain"):
            await self._send_reply(update, "Module Second Brain đang tắt.")
            return
        query = " ".join(context.args or []).strip()
        notes = await self._brain.find_notes(query, limit=8)
        if not notes:
            await self._send_reply(update, "Không tìm thấy ghi chú phù hợp.")
            return
        lines = [f"Tìm thấy {len(notes)} ghi chú:"]
        for n in notes:
            lines.append(f"• #{n['id']} [{n['title']}]: {n['content'][:160]}")
        await self._send_reply(update, "\n".join(lines))

    async def cmd_remind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update) or not update.effective_chat:
            return
        if not await self._is_module_enabled("brain"):
            await self._send_reply(update, "Module Second Brain đang tắt.")
            return
        raw = " ".join(context.args or []).strip()
        try:
            rem = await self._brain.schedule_reminder(update.effective_chat.id, raw)
        except ValueError as exc:
            await self._send_reply(update, str(exc))
            return
        await self._send_reply(
            update, f"Đã hẹn nhắc #{rem['id']} lúc {rem['remind_at']}: {rem['message']}"
        )

    async def _handle_finance_cmd(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str
    ) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("finance"):
            await self._send_reply(update, "Module Tài chính đang tắt.")
            return
        raw = " ".join(context.args or []).strip()
        try:
            tx = await self._finance.record_from_text(raw, kind)
        except ValueError as exc:
            await self._send_reply(update, str(exc))
            return
        amt_str = format_amount(int(tx["amount_minor"]), str(tx["currency"]))
        label = "Chi" if kind == "expense" else "Thu"
        await self._send_reply(
            update, f"Đã ghi {label}: {amt_str} [{tx['category']}] — {tx['note']}"
        )

    async def cmd_chi(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_finance_cmd(update, context, "expense")

    async def cmd_thu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_finance_cmd(update, context, "income")

    async def cmd_thongke(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("finance"):
            await self._send_reply(update, "Module Tài chính đang tắt.")
            return
        month = context.args[0].strip() if context.args else None
        summary = await self._finance.monthly_report(month)
        lines = [f"Thống kê tài chính tháng {summary['month']}:"]
        if not summary["totals"]:
            lines.append("Chưa có giao dịch nào trong tháng này.")
        else:
            for t in summary["totals"]:
                kind_lbl = "Tổng chi" if t["kind"] == "expense" else "Tổng thu"
                lines.append(
                    f"• {kind_lbl}: {format_amount(int(t['total_minor']), str(t['currency']))}"
                )
            lines.append("\nTheo danh mục:")
            for c in summary["by_category"][:10]:
                amt_fmt = format_amount(int(c["total_minor"]), str(c["currency"]))
                lines.append(
                    f"  - [{c['kind']}] {c['category']}: {amt_fmt} ({c['tx_count']} GD)"
                )
        await self._send_reply(update, "\n".join(lines))

    async def cmd_tomtat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update) or not update.effective_chat:
            return
        if not await self._is_module_enabled("digest"):
            await self._send_reply(update, "Module Tóm tắt Link/RSS đang tắt.")
            return
        if not context.args:
            await self._send_reply(update, "Dùng: `/tomtat https://example.com/article`")
            return
        url = context.args[0].strip()
        try:
            digest = await self._run_with_typing(
                update.effective_chat.id, context.bot, self._digest.summarize_url(url)
            )
        except (UnsafeURLError, ValueError, LLMError) as exc:
            await self._send_reply(update, f"Không thể tóm tắt: {exc}")
            return
        await self._send_reply(update, f"{digest['title']}\n\n{digest['summary']}")

    async def cmd_feed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("digest"):
            await self._send_reply(update, "Module Tóm tắt Link/RSS đang tắt.")
            return
        if not context.args:
            feeds = await self._repo.list_feeds()
            if not feeds:
                await self._send_reply(
                    update, "Chưa có nguồn RSS nào. Dùng `/feed https://...` để thêm."
                )
                return
            lines = ["Danh sách nguồn tin đã lưu:"] + [
                f"• #{f['id']} {f['title']} ({f['url']})" for f in feeds
            ]
            await self._send_reply(update, "\n".join(lines))
            return
        url = context.args[0].strip()
        try:
            feed = await self._digest.subscribe_feed(url)
            items = await self._digest.fetch_feed_headlines(url, limit=5)
        except (UnsafeURLError, Exception) as exc:
            await self._send_reply(update, f"Lỗi thêm feed: {exc}")
            return
        lines = [f"Đã theo dõi feed #{feed['id']}: {feed['url']}", "Tin mới nhất:"]
        for it in items:
            lines.append(f"• {it['title']} — {it['url']}")
        await self._send_reply(update, "\n".join(lines))

    async def cmd_pc(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        if not await self._is_module_enabled("remote"):
            await self._send_reply(
                update,
                "Module PC/Docker Remote đang TẮT để bảo mật. Hãy bật trong TeleMind Hub nếu cần.",
            )
            return
        stats = self._remote.get_host_stats()
        msg = (
            f"Trạng thái máy local ({stats['platform']}):\n"
            f"• CPU: {stats['cpu_percent']}%\n"
            f"• RAM: {stats['ram_used_gb']}/{stats['ram_total_gb']} GB ({stats['ram_percent']}%)\n"
            f"• Disk trống: {stats['disk_free_gb']}/{stats['disk_total_gb']} GB"
        )
        await self._send_reply(update, msg)

    async def cmd_docker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            not await self._authorize(update)
            or not update.effective_user
            or not update.effective_message
        ):
            return
        if not await self._is_module_enabled("remote"):
            await self._send_reply(update, "Module PC/Docker Remote đang TẮT.")
            return
        pending = self._remote.request_confirmation(update.effective_user.id, "docker_ps")
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Xác nhận chạy (60s)", callback_data=f"rm_ok:{pending.token}"
                    ),
                    InlineKeyboardButton("Hủy", callback_data=f"rm_no:{pending.token}"),
                ]
            ]
        )
        await update.effective_message.reply_text(
            "Xác nhận chạy `docker ps -a` trên máy local?", reply_markup=kb
        )

    async def cmd_dockerlogs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            not await self._authorize(update)
            or not update.effective_user
            or not update.effective_message
        ):
            return
        if not await self._is_module_enabled("remote"):
            await self._send_reply(update, "Module PC/Docker Remote đang TẮT.")
            return
        if not context.args:
            await self._send_reply(update, "Dùng: `/dockerlogs <tên_container>`")
            return
        try:
            pending = self._remote.request_confirmation(
                update.effective_user.id, "docker_logs", context.args[0]
            )
        except ValueError as exc:
            await self._send_reply(update, str(exc))
            return
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Xác nhận đọc log (60s)", callback_data=f"rm_ok:{pending.token}"
                    ),
                    InlineKeyboardButton("Hủy", callback_data=f"rm_no:{pending.token}"),
                ]
            ]
        )
        await update.effective_message.reply_text(
            f"Xác nhận đọc 40 dòng log gần nhất của container `{pending.arg}`?",
            reply_markup=kb,
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorize(update):
            return
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not query.data:
            return
        await query.answer()

        if query.data.startswith("rm_no:"):
            token = query.data.split(":", 1)[1]
            self._remote.cancel_confirmation(token, user.id)
            await query.edit_message_text("Đã hủy thao tác.")
            return

        if query.data.startswith("rm_ok:"):
            token = query.data.split(":", 1)[1]
            try:
                output = await self._remote.confirm_and_execute(token, user.id)
                await query.edit_message_text(f"Kết quả:\n{output[:3500]}")
            except (ValueError, PermissionError, RuntimeError) as exc:
                await query.edit_message_text(f"Thao tác thất bại: {exc}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            not await self._authorize(update)
            or not update.effective_message
            or not update.effective_chat
        ):
            return
        if not await self._is_module_enabled("chat"):
            await self._send_reply(update, "Module AI Chat đang tắt.")
            return

        msg = update.effective_message
        chat_id = update.effective_chat.id
        text = (msg.text or msg.caption or "").strip()

        image_bytes: bytes | None = None
        image_mime: str | None = None
        audio_bytes: bytes | None = None
        audio_mime: str | None = None
        pdf_bytes: bytes | None = None
        pdf_name: str | None = None

        if msg.photo:
            photo = msg.photo[-1]
            if photo.file_size and photo.file_size > MAX_TG_FILE_BYTES:
                await self._send_reply(update, "Ảnh vượt quá giới hạn 10 MB.")
                return
            tg_file = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await tg_file.download_as_bytearray())
            image_mime = "image/jpeg"

            if text.lower().startswith(("/bill", "/chi")) and await self._is_module_enabled(
                "finance"
            ):
                try:
                    tx = await self._finance.record_from_receipt_image(
                        image_bytes, image_mime, text
                    )
                    amt = format_amount(int(tx["amount_minor"]), str(tx["currency"]))
                    await self._send_reply(
                        update,
                        f"Đã đọc hóa đơn & lưu chi tiêu: {amt} [{tx['category']}] — {tx['note']}",
                    )
                except (LLMError, ValueError) as exc:
                    await self._send_reply(update, f"Không lưu được hóa đơn: {exc}")
                return

        elif msg.voice or msg.audio:
            voice_obj = msg.voice or msg.audio
            assert voice_obj is not None
            if voice_obj.file_size and voice_obj.file_size > MAX_TG_FILE_BYTES:
                await self._send_reply(update, "File âm thanh vượt quá giới hạn 10 MB.")
                return
            tg_file = await context.bot.get_file(voice_obj.file_id)
            audio_bytes = bytes(await tg_file.download_as_bytearray())
            audio_mime = voice_obj.mime_type or "audio/ogg"

        elif msg.document:
            doc = msg.document
            if doc.file_size and doc.file_size > MAX_TG_FILE_BYTES:
                await self._send_reply(update, "File đính kèm vượt quá giới hạn 10 MB.")
                return
            if doc.mime_type == "application/pdf" or (doc.file_name or "").lower().endswith(".pdf"):
                tg_file = await context.bot.get_file(doc.file_id)
                pdf_bytes = bytes(await tg_file.download_as_bytearray())
                pdf_name = (doc.file_name or "document.pdf").replace("/", "_")

        try:
            res = await self._run_with_typing(
                chat_id,
                context.bot,
                self._chat.reply(
                    chat_id,
                    text,
                    image_bytes=image_bytes,
                    image_mime=image_mime,
                    audio_bytes=audio_bytes,
                    audio_mime=audio_mime,
                    pdf_bytes=pdf_bytes,
                    pdf_name=pdf_name,
                ),
            )
        except (ProviderNotConfiguredError, BudgetExceededError, LLMError) as exc:
            await self._send_reply(update, f"Lỗi AI: {exc}")
            return

        await self._send_reply(update, res.text)

    # --- Lifecycle ---
    async def start(self) -> None:
        """Start Telegram bot polling if a token is configured."""
        if self._settings.disable_bot_polling:
            self.running = False
            return

        token = await self._repo.get_secret("telegram", self._settings.telegram_bot_token)
        if not token:
            self.running = False
            self.last_error = "TELEGRAM_BOT_TOKEN chưa được cấu hình."
            return

        await self.stop()
        try:
            app = Application.builder().token(token).concurrent_updates(True).build()
            app.add_handler(CommandHandler("start", self.cmd_start))
            app.add_handler(CommandHandler("help", self.cmd_start))
            app.add_handler(CommandHandler("model", self.cmd_model))
            app.add_handler(CommandHandler("mode", self.cmd_mode))
            app.add_handler(CommandHandler("clear", self.cmd_clear))
            app.add_handler(CommandHandler("note", self.cmd_note))
            app.add_handler(CommandHandler("find", self.cmd_find))
            app.add_handler(CommandHandler("remind", self.cmd_remind))
            app.add_handler(CommandHandler("chi", self.cmd_chi))
            app.add_handler(CommandHandler("thu", self.cmd_thu))
            app.add_handler(CommandHandler("thongke", self.cmd_thongke))
            app.add_handler(CommandHandler("tomtat", self.cmd_tomtat))
            app.add_handler(CommandHandler("feed", self.cmd_feed))
            app.add_handler(CommandHandler("pc", self.cmd_pc))
            app.add_handler(CommandHandler("docker", self.cmd_docker))
            app.add_handler(CommandHandler("dockerlogs", self.cmd_dockerlogs))
            app.add_handler(CallbackQueryHandler(self.handle_callback))
            app.add_handler(
                MessageHandler(
                    filters.TEXT
                    | filters.PHOTO
                    | filters.Document.ALL
                    | filters.VOICE
                    | filters.AUDIO,
                    self.handle_message,
                )
            )

            await app.initialize()
            await app.start()
            if app.updater:
                await app.updater.start_polling(drop_pending_updates=True)
            self._app = app
            self.running = True
            self.last_error = ""
            await self._repo.log_audit("system", "telegram_bot", "started", "polling_active")
        except Exception as exc:
            self.running = False
            self.last_error = str(exc)
            logger.exception("Failed to start Telegram polling")
            await self._repo.log_audit("system", "telegram_bot", "error", str(exc)[:300])

    async def stop(self) -> None:
        """Stop Telegram polling cleanly."""
        if self._app is None:
            self.running = False
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        finally:
            self._app = None
            self.running = False

    async def reload(self) -> None:
        """Restart bot polling after configuration changes."""
        await self.stop()
        await self.start()
