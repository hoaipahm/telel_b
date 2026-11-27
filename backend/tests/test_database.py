"""Database constraints, FTS5 search, and integer finance aggregation tests."""

from __future__ import annotations

import aiosqlite
import pytest
from app.db.repositories import Repository


async def test_notes_fts_and_punctuation_fallback(repo: Repository) -> None:
    await repo.create_note("Docker Guide", "Build multi-stage Dockerfile safely", "docker, devops")
    await repo.create_note("C++ Tips", "Use smart pointers in C++20", "cpp")

    hits = await repo.search_notes("Dockerfile")
    assert len(hits) == 1
    assert hits[0]["title"] == "Docker Guide"

    cpp_hits = await repo.search_notes("C++")
    assert len(cpp_hits) == 1
    assert cpp_hits[0]["title"] == "C++ Tips"


async def test_transaction_constraints_reject_zero_or_invalid_kind(repo: Repository) -> None:
    with pytest.raises(aiosqlite.IntegrityError):
        await repo.add_transaction("expense", 0, "Food", "zero")

    with pytest.raises(aiosqlite.IntegrityError):
        await repo.add_transaction("transfer", 50000, "Food", "bad kind")


async def test_finance_summary_exact_integers(repo: Repository) -> None:
    await repo.add_transaction(
        "expense", 55000, "Ăn uống", "Cơm trưa", occurred_at="2026-11-10T05:00:00+00:00"
    )
    await repo.add_transaction(
        "expense", 45000, "Ăn uống", "Cà phê", occurred_at="2026-11-12T05:00:00+00:00"
    )
    await repo.add_transaction(
        "income", 15000000, "Lương", "Lương tháng 11", occurred_at="2026-11-01T05:00:00+00:00"
    )

    summary = await repo.finance_summary("2026-11")
    totals = {row["kind"]: row["total_minor"] for row in summary["totals"]}
    assert totals["expense"] == 100000
    assert totals["income"] == 15000000
