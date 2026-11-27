"""Shared pytest fixtures for TeleMind backend tests."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from app.config import Settings
from app.db.database import Database
from app.db.repositories import Repository
from app.security.crypto import SecretVault


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Create isolated settings pointing at a temporary directory."""
    return Settings(
        data_dir=tmp_path / "data",
        allowed_telegram_user_ids="123456789",
        web_admin_token=secrets.token_urlsafe(16),
        disable_bot_polling=True,
    )


@pytest.fixture
async def repo(tmp_settings: Settings) -> Repository:
    """Provide an initialized Repository with fresh SQLite DB and Fernet vault."""
    db = Database(tmp_settings.db_path)
    await db.initialize()
    vault = SecretVault.from_env_or_file("", tmp_settings.master_key_path)
    return Repository(db, vault)
