"""Core AI chat module with search grounding, URL ingestion, audio, and tool actions."""

from __future__ import annotations

import base64
import io
import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from app.db.repositories import Repository
from app.llm.base import ChatMessage, LLMRequest, LLMResponse
from app.llm.router import LLMRouter
from app.modules.digest import extract_readable_html
from app.modules.finance import format_amount
from app.security.ssrf import UnsafeURLError, safe_fetch_text

if TYPE_CHECKING:
    from app.modules.brain import SecondBrainService
    from app.modules.finance import FinanceService

URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>()\"']+", re.I)
MUSIC_INTENT_RE = re.compile(
    r"\b(youtube|ytb|bài hát|bai hat|ca khúc|ca khuc|nhạc|nhac|mv|lyrics|nghe bài|song)\b",
    re.I,
)
ACTION_TAG_RE = re.compile(r"\[\[TELEMIND_ACTION:(\{.*?\})\]\]", re.S)


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 12000) -> str:
    """Extract readable text from an uploaded PDF cleanly within a character cap."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    chunks: list[str] = []
    total = 0
    for page in reader.pages[:20]:
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        piece = text[:remaining]
        chunks.append(piece)
        total += len(piece)
    return "\n\n".join(chunks).strip()


class ChatService:
    """Handles conversational memory, live search grounding, audio, and tool execution."""

    def __init__(
        self,
        repo: Repository,
        router: LLMRouter,
        timezone: str = "Asia/Ho_Chi_Minh",
        *,
        brain_svc: SecondBrainService | None = None,
        finance_svc: FinanceService | None = None,
    ) -> None:
        self._repo = repo
        self._router = router
        self._tz = timezone
        self._brain = brain_svc
        self._finance = finance_svc

    async def _enrich_pasted_url(self, prompt_text: str) -> str:
        """Fetch public URL content when a user pastes a link directly into normal chat."""
        match = URL_IN_TEXT_RE.search(prompt_text)
        if not match:
            return ""
        raw_url = match.group(0).rstrip(".,;)")
        try:
            final_url, content_type, body = await safe_fetch_text(raw_url, timeout_seconds=6.0)
        except (UnsafeURLError, Exception):
            return ""
        if "html" in content_type.lower():
            title, readable = extract_readable_html(body, max_chars=4500)
        else:
            title, readable = final_url, body[:4500]
        if not readable.strip():
            return ""
        return f"\n\n[Nội dung đọc từ URL {final_url} — {title}]:\n{readable}"

    async def _resolve_reminder_chat_id(self, chat_id: int) -> int:
        if chat_id > 0:
            return chat_id
        db_ids = await self._repo.get_setting("allowed_telegram_user_ids", [])
        if isinstance(db_ids, list):
            for item in db_ids:
                if str(item).isdigit() and int(item) > 0:
                    return int(item)
        return chat_id

    async def _run_action(self, raw_json: str, chat_id: int) -> str:
        """Validate and execute one internal TeleMind action emitted by the assistant."""
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return ""
        if not isinstance(payload, dict):
            return ""

        tool = str(payload.get("tool") or "").strip().lower()
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            return ""
        modules: dict[str, bool] = await self._repo.get_setting("modules", {})

        try:
            if tool == "create_note" and self._brain and modules.get("brain"):
                title = str(args.get("title") or "").strip()
                content = str(args.get("content") or "").strip()
                tags = str(args.get("tags") or "").strip()
                raw = f"{title} | {content}" if title and content else (content or title)
                if tags:
                    raw = f"{raw} #{tags.replace(',', ' #')}"
                note = await self._brain.add_note_from_text(raw)
                return f"✓ Đã lưu ghi chú #{note['id']}: {note['title']}"

            if tool == "search_notes" and self._brain and modules.get("brain"):
                query = str(args.get("query") or "").strip()
                notes = await self._brain.find_notes(query, limit=5)
                if not notes:
                    return "Không tìm thấy ghi chú phù hợp trong Second Brain."
                lines = [f"Ghi chú tìm thấy ({len(notes)}):"] + [
                    f"• #{n['id']} **{n['title']}**: {n['content'][:140]}" for n in notes
                ]
                return "\n".join(lines)

            if tool == "create_reminder" and self._brain and modules.get("brain"):
                when_msg = str(args.get("raw") or args.get("when_and_message") or "").strip()
                target_chat = await self._resolve_reminder_chat_id(chat_id)
                if target_chat <= 0:
                    return "Chưa có Telegram User ID trong Allowlist để gửi nhắc việc."
                rem = await self._brain.schedule_reminder(target_chat, when_msg)
                return f"✓ Đã hẹn nhắc #{rem['id']} lúc {rem['remind_at']}: {rem['message']}"

            if tool in ("log_expense", "log_income") and self._finance and modules.get("finance"):
                kind = "income" if tool == "log_income" else "expense"
                entry = str(args.get("raw") or args.get("entry") or "").strip()
                tx = await self._finance.record_from_text(entry, kind)
                amt = format_amount(int(tx["amount_minor"]), str(tx["currency"]))
                lbl = "Thu" if kind == "income" else "Chi"
                return f"✓ Đã ghi {lbl}: {amt} [{tx['category']}] — {tx['note']}"

            if tool == "finance_summary" and self._finance and modules.get("finance"):
                month = str(args.get("month") or "").strip() or None
                summary = await self._finance.monthly_report(month)
                if not summary["totals"]:
                    return f"Tháng {summary['month']} chưa có giao dịch nào."
                parts = [f"Thống kê tháng {summary['month']}:"] + [
                    f"• {'Tổng chi' if t['kind'] == 'expense' else 'Tổng thu'}: "
                    f"{format_amount(int(t['total_minor']), str(t['currency']))}"
                    for t in summary["totals"]
                ]
                return "\n".join(parts)
        except Exception as exc:
            return f"(Không thực thi được thao tác `{tool}`: {exc})"
        return ""

    def _build_system_prompt(self, base_persona: str) -> str:
        now_local = datetime.now(ZoneInfo(self._tz)).strftime("%Y-%m-%d %H:%M")
        tool_guide = ""
        if self._brain or self._finance:
            tool_guide = (
                "\nNếu người dùng yêu cầu bằng ngôn ngữ tự nhiên một trong các hành động sau, "
                "hãy trả lời ngắn gọn VÀ gắn thêm ĐÚNG 1 dòng ở cuối theo định dạng:\n"
                '[[TELEMIND_ACTION:{"tool":"<tên>","args":{...}}]]\n'
                "- create_note: {\"title\":\"...\",\"content\":\"...\",\"tags\":\"...\"}\n"
                "- search_notes: {\"query\":\"...\"}\n"
                "- create_reminder: {\"raw\":\"30m nội dung\" hoặc \"09:30 nội dung\" "
                "hoặc \"YYYY-MM-DD HH:MM nội dung\"}\n"
                "- log_expense: {\"raw\":\"55k ăn trưa\"}\n"
                "- log_income: {\"raw\":\"15tr lương\"}\n"
                "- finance_summary: {\"month\":\"YYYY-MM\" (tùy chọn)}\n"
                "Chỉ dùng [[TELEMIND_ACTION:...]] khi người dùng thực sự muốn lưu/tìm/hẹn việc."
            )
        return (
            f"{base_persona}\n"
            f"Thời gian hiện tại: {now_local} ({self._tz}). "
            "Khi cần thông tin mới, bài hát hoặc đường dẫn, hãy dùng công cụ tìm kiếm nếu có; "
            "tuyệt đối KHÔNG bịa URL hoặc mã video YouTube từ trí nhớ."
            f"{tool_guide}"
        )

    async def reply(
        self,
        chat_id: int,
        user_text: str,
        *,
        image_bytes: bytes | None = None,
        image_mime: str | None = None,
        audio_bytes: bytes | None = None,
        audio_mime: str | None = None,
        pdf_bytes: bytes | None = None,
        pdf_name: str | None = None,
    ) -> LLMResponse:
        """Persist user turn, call configured LLM with grounding/audio/tools, and store reply."""
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        personas: dict[str, str] = await self._repo.get_setting("personas", {})
        active_persona = str(ai_cfg.get("active_persona", "assistant"))
        base_persona = personas.get(
            active_persona,
            "Bạn là trợ lý AI cá nhân thông minh, súc tích và trung thực.",
        )
        system_prompt = self._build_system_prompt(base_persona)

        prompt_text = user_text.strip()
        if pdf_bytes:
            extracted = extract_pdf_text(pdf_bytes)
            label = pdf_name or "document.pdf"
            if extracted:
                base_ask = prompt_text or "Hãy tóm tắt và phân tích tài liệu PDF này."
                prompt_text = f"{base_ask}\n\n[PDF: {label}]\n{extracted}"
            else:
                prompt_text = (
                    f"{prompt_text}\n\n"
                    f"[PDF {label} không có text trích xuất được (có thể là file scan ảnh).]"
                )
        elif prompt_text and not image_bytes and not audio_bytes:
            prompt_text += await self._enrich_pasted_url(prompt_text)

        history_rows = await self._repo.get_recent_messages(chat_id, limit=10)
        messages = [
            ChatMessage(role=str(r["role"]), content=str(r["content"]))
            for r in history_rows
            if r["role"] in ("user", "assistant")
        ]

        img_b64 = base64.b64encode(image_bytes).decode("ascii") if image_bytes else None
        aud_b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None
        fallback_label = (
            "Hãy nghe và phản hồi tin nhắn thoại này bằng tiếng Việt."
            if aud_b64
            else "Hãy phân tích hình ảnh này."
        )
        messages.append(
            ChatMessage(
                role="user",
                content=prompt_text or fallback_label,
                image_base64=img_b64,
                image_mime=image_mime,
                audio_base64=aud_b64,
                audio_mime=audio_mime,
            )
        )

        stored_user = user_text.strip() or ("[Tin nhắn thoại]" if aud_b64 else "[Hình ảnh]")
        await self._repo.add_message(chat_id, "user", stored_user)
        res = await self._router.complete(
            LLMRequest(
                messages=messages,
                system_prompt=system_prompt,
                use_web_search=True,
            )
        )

        cleaned_reply = res.text
        action_match = ACTION_TAG_RE.search(cleaned_reply)
        action_note = ""
        if action_match:
            action_note = await self._run_action(action_match.group(1), chat_id)
            cleaned_reply = ACTION_TAG_RE.sub("", cleaned_reply).strip()

        if action_note:
            cleaned_reply = f"{cleaned_reply}\n\n{action_note}".strip()

        final_text = _append_verified_links(cleaned_reply, res.sources, user_text)
        await self._repo.add_message(
            chat_id,
            "assistant",
            final_text,
            provider=res.provider,
            model=res.model,
            tokens_used=res.input_tokens + res.output_tokens,
        )
        return LLMResponse(
            text=final_text,
            provider=res.provider,
            model=res.model,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            raw_finish_reason=res.raw_finish_reason,
            sources=res.sources,
        )


def _append_verified_links(
    reply_text: str,
    sources: tuple[tuple[str, str], ...],
    user_query: str,
) -> str:
    """Append real grounded citations and guaranteed YouTube search fallback if requested."""
    parts = [reply_text.rstrip()]
    has_youtube_link = "youtube.com/" in reply_text or "youtu.be/" in reply_text

    if sources:
        source_lines = []
        for title, uri in sources[:4]:
            if uri not in reply_text:
                source_lines.append(f"• [{title}]({uri})")
            if "youtube.com/" in uri or "youtu.be/" in uri:
                has_youtube_link = True
        if source_lines:
            parts.append("Nguồn tham khảo:\n" + "\n".join(source_lines))

    clean_query = user_query.strip()
    if clean_query and MUSIC_INTENT_RE.search(clean_query) and not has_youtube_link:
        yt_search = f"https://www.youtube.com/results?search_query={quote_plus(clean_query[:120])}"
        parts.append(f"Tìm & phát trực tiếp trên YouTube:\n{yt_search}")

    return "\n\n".join(p for p in parts if p)
