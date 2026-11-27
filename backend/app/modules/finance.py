"""Personal Finance module using exact integer minor units (never float)."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.repositories import Repository
from app.llm.base import ChatMessage, LLMError, LLMRequest
from app.llm.router import LLMRouter

AMOUNT_TOKEN_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>tr|trieu|triệu|m|k|nghin|nghìn|ngan|ngàn|usd|đ|d|vnd)?\b",
    re.I,
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Ăn uống": (
        "ăn",
        "cơm",
        "phở",
        "bún",
        "cafe",
        "cà phê",
        "trà",
        "nhậu",
        "lunch",
        "dinner",
        "food",
    ),
    "Di chuyển": ("xăng", "grab", "be", "taxi", "xe", "gửi xe", "bus", "vé"),
    "Mua sắm": ("mua", "shopee", "lazada", "áo", "quần", "đồ", "giày"),
    "Hóa đơn & Nhà cửa": ("điện", "nước", "internet", "wifi", "nhà", "thuê", "bill", "rác"),
    "Sức khỏe": ("thuốc", "khám", "gym", "bệnh viện"),
    "Giải trí": ("phim", "game", "netflix", "du lịch", "spotify"),
    "Lương & Thu nhập": ("lương", "thưởng", "freelance", "bán", "hoàn tiền", "thu"),
}


def parse_amount_to_integer(raw_num: str, unit: str | None) -> tuple[int, str]:
    """Convert Vietnamese/English money shorthand into exact integer units using Decimal."""
    normalized = raw_num.replace(",", ".")
    if normalized.count(".") > 1:
        normalized = normalized.replace(".", "")
    elif "." in normalized:
        parts = normalized.split(".")
        if len(parts[1]) == 3 and not unit:
            normalized = "".join(parts)

    try:
        dec = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Số tiền không hợp lệ: {raw_num}") from exc

    u = (unit or "").lower()
    currency = "VND"
    multiplier = Decimal("1")
    if u in ("k", "nghin", "nghìn", "ngan", "ngàn"):
        multiplier = Decimal("1000")
    elif u in ("tr", "trieu", "triệu", "m"):
        multiplier = Decimal("1000000")
    elif u == "usd":
        currency = "USD"
        multiplier = Decimal("100")

    minor = int((dec * multiplier).quantize(Decimal("1")))
    if minor <= 0:
        raise ValueError("Số tiền phải lớn hơn 0.")
    return minor, currency


def infer_category(note: str, kind: str) -> str:
    """Infer a friendly category from transaction description keywords."""
    lower = note.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "Thu nhập khác" if kind == "income" else "Chi tiêu khác"


def parse_transaction_text(raw: str, kind: str) -> tuple[int, str, str, str]:
    """Parse text like '55k ăn trưa' into `(amount_minor, currency, category, note)`."""
    text = raw.strip()
    match = AMOUNT_TOKEN_RE.search(text)
    if not match:
        raise ValueError(
            "Không tìm thấy số tiền (ví dụ: `/chi 55k ăn trưa` hoặc `/thu 15tr lương`)."
        )

    amount_minor, currency = parse_amount_to_integer(match.group("num"), match.group("unit"))
    remaining = (text[: match.start()] + " " + text[match.end() :]).strip(" -:,")
    note = remaining or ("Khoản thu" if kind == "income" else "Khoản chi")
    category = infer_category(note, kind)
    return amount_minor, currency, category, note


def format_amount(amount_minor: int, currency: str) -> str:
    """Format integer minor units for display."""
    if currency == "USD":
        dollars = Decimal(amount_minor) / Decimal("100")
        return f"${dollars:,.2f}"
    return f"{amount_minor:,} {currency}"


class FinanceService:
    """Handles expense/income logging, receipt OCR extraction, monthly summaries, and CSV export."""

    def __init__(self, repo: Repository, router: LLMRouter) -> None:
        self._repo = repo
        self._router = router

    async def record_from_text(self, raw: str, kind: str) -> dict[str, Any]:
        amount_minor, currency, category, note = parse_transaction_text(raw, kind)
        return await self._repo.add_transaction(
            kind=kind,
            amount_minor=amount_minor,
            currency=currency,
            category=category,
            note=note,
        )

    async def record_from_receipt_image(
        self,
        image_bytes: bytes,
        image_mime: str,
        caption: str = "",
    ) -> dict[str, Any]:
        """Extract transaction data from a receipt photo using multimodal LLM."""
        import base64

        b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "Đọc hóa đơn trong ảnh và trả về DUY NHẤT JSON hợp lệ với schema: "
            '{"kind":"expense","amount_vnd":<số nguyên>,'
            '"category":"<danh mục ngắn>","note":"<tên quán/món>"}. '
            f"Ghi chú thêm của người dùng: {caption or 'không có'}."
        )
        res = await self._router.complete(
            LLMRequest(
                messages=[
                    ChatMessage(
                        role="user", content=prompt, image_base64=b64, image_mime=image_mime
                    )
                ],
                temperature=0.1,
                max_tokens=300,
            )
        )
        json_match = re.search(r"\{.*\}", res.text, re.S)
        if not json_match:
            raise LLMError(
                f"Không trích xuất được dữ liệu hóa đơn từ phản hồi AI: {res.text[:150]}"
            )
        parsed = json.loads(json_match.group(0))
        amount = int(parsed.get("amount_vnd", 0))
        if amount <= 0:
            raise ValueError("Số tiền trích từ hóa đơn không hợp lệ.")
        return await self._repo.add_transaction(
            kind="expense",
            amount_minor=amount,
            currency="VND",
            category=str(parsed.get("category") or "Mua sắm")[:40],
            note=str(parsed.get("note") or caption or "Hóa đơn ảnh")[:160],
        )

    async def monthly_report(self, month_prefix: str | None = None) -> dict[str, Any]:
        month = month_prefix or datetime.now(UTC).strftime("%Y-%m")
        return await self._repo.finance_summary(month)

    async def export_csv(self, month_prefix: str | None = None) -> str:
        rows = await self._repo.list_transactions(month_prefix=month_prefix, limit=500)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "kind", "amount_minor", "currency", "category", "note", "occurred_at"]
        )
        for r in rows:
            writer.writerow(
                [
                    r["id"],
                    r["kind"],
                    r["amount_minor"],
                    r["currency"],
                    r["category"],
                    r["note"],
                    r["occurred_at"],
                ]
            )
        return buf.getvalue()
