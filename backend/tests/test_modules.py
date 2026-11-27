"""Modular capability tests: Second Brain, Finance parsing, Digest HTML/RSS, Remote 2FA."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.bot.telegram_app import markdown_to_telegram_html
from app.db.repositories import Repository
from app.modules.brain import SecondBrainService, parse_note_input, parse_reminder_input
from app.modules.chat import ChatService, _append_verified_links
from app.modules.digest import extract_readable_html, parse_rss_items
from app.modules.finance import FinanceService, format_amount, parse_transaction_text
from app.modules.remote import RemoteService


def test_parse_note_and_reminder() -> None:
    title, content, tags = parse_note_input(
        "Docker tips | Always use non-root user #docker #security"
    )
    assert title == "Docker tips"
    assert "non-root" in content
    assert tags == "docker, security"

    fixed_now = datetime(2026, 11, 27, 4, 0, tzinfo=UTC)
    dt, msg = parse_reminder_input("30m kiểm tra build", now_utc=fixed_now)
    assert msg == "kiểm tra build"
    assert int((dt - fixed_now).total_seconds()) == 1800


def test_finance_text_parsing_and_formatting() -> None:
    amt, cur, cat, note = parse_transaction_text("55k ăn trưa bún chả", "expense")
    assert amt == 55000
    assert cur == "VND"
    assert cat == "Ăn uống"
    assert "bún chả" in note
    assert format_amount(amt, cur) == "55,000 VND"

    amt2, cur2, _, _ = parse_transaction_text("1.5tr tiền nhà", "expense")
    assert amt2 == 1500000
    assert cur2 == "VND"

    amt3, cur3, _, _ = parse_transaction_text("12.50 USD cloud server", "expense")
    assert amt3 == 1250
    assert cur3 == "USD"
    assert format_amount(amt3, cur3) == "$12.50"


def test_digest_html_strips_scripts_and_parses_rss() -> None:
    html = (
        "<html><head><title>Test Post</title><script>alert(1)</script></head>"
        "<body><p>Hello world</p></body></html>"
    )
    title, body = extract_readable_html(html)
    assert title == "Test Post"
    assert "alert(1)" not in body
    assert "Hello world" in body

    rss = "<rss><channel><item><title>Item 1</title><link>https://example.com/1</link></item></channel></rss>"
    items = parse_rss_items(rss)
    assert items == [{"title": "Item 1", "url": "https://example.com/1"}]


async def test_remote_confirmation_ownership_and_single_use(repo: Repository) -> None:
    svc = RemoteService(repo)
    pending = svc.request_confirmation(user_id=123, preset_id="docker_logs", arg="web-app")

    with pytest.raises(PermissionError):
        await svc.confirm_and_execute(pending.token, user_id=999)

    assert svc.cancel_confirmation(pending.token, user_id=123)
    with pytest.raises(ValueError):
        await svc.confirm_and_execute(pending.token, user_id=123)


def test_chat_verified_links_and_youtube_search_fallback() -> None:
    out = _append_verified_links(
        "Bạn có thể nghe bài Chạy Ngay Đi của Sơn Tùng M-TP.",
        (("Wikipedia", "https://vi.wikipedia.org/wiki/Son_Tung"),),
        "tìm bài hát chạy ngay đi trên youtube",
    )
    assert "https://vi.wikipedia.org/wiki/Son_Tung" in out
    assert "https://www.youtube.com/results?search_query=" in out


def test_markdown_to_telegram_html_escapes_unsafe_tags() -> None:
    rendered = markdown_to_telegram_html(
        "**Xin chào** <script>alert(1)</script> `[link](https://example.com)` "
        "và [YouTube](https://youtube.com/watch?v=123)"
    )
    assert "<b>Xin chào</b>" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<code>[link](https://example.com)</code>" in rendered
    assert '<a href="https://youtube.com/watch?v=123">YouTube</a>' in rendered


async def test_chat_service_executes_natural_language_actions(repo: Repository) -> None:
    from app.config import Settings
    from app.llm.router import LLMRouter

    brain = SecondBrainService(repo)
    router = LLMRouter(repo, Settings())
    finance = FinanceService(repo, router)
    chat = ChatService(repo, router, brain_svc=brain, finance_svc=finance)

    msg1 = await chat._run_action(
        '{"tool":"create_note","args":{"title":"Wifi","content":"pass 1234","tags":"home"}}',
        chat_id=123,
    )
    assert "Đã lưu ghi chú" in msg1
    msg2 = await chat._run_action(
        '{"tool":"log_expense","args":{"raw":"45k bún bò"}}',
        chat_id=123,
    )
    assert "45,000 VND" in msg2
    await router.close()
