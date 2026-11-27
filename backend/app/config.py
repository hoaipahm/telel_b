"""Application configuration and runtime settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed runtime settings with safe local-first defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    allowed_telegram_user_ids: str = Field(default="")
    telegram_bot_token: str = Field(default="")
    gemini_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    web_admin_token: str = Field(default="")
    bot_master_key: str = Field(default="")

    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)
    allowed_origins: str = Field(default="http://127.0.0.1:3000,http://localhost:3000")

    data_dir: Path = Field(default=Path("./data"))
    daily_llm_request_cap: int = Field(default=200, ge=1, le=100000)
    daily_llm_token_cap: int = Field(default=500000, ge=1000, le=50000000)
    timezone: str = Field(default="Asia/Ho_Chi_Minh")
    disable_bot_polling: bool = Field(default=False)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _coerce_data_dir(cls, value: str | Path) -> Path:
        return Path(value)

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.data_dir / "telemind.db"

    @property
    def master_key_path(self) -> Path:
        """Path to the local Fernet master key file."""
        return self.data_dir / "master.key"

    @property
    def admin_token_path(self) -> Path:
        """Path to the auto-generated local admin token file."""
        return self.data_dir / "admin.token"

    def parsed_allowed_user_ids(self) -> set[int]:
        """Parse comma-separated Telegram numeric user IDs safely."""
        ids: set[int] = set()
        for raw in self.allowed_telegram_user_ids.split(","):
            token = raw.strip()
            if not token:
                continue
            if token.isdigit():
                ids.add(int(token))
        return ids

    def parsed_allowed_origins(self) -> list[str]:
        """Parse CORS allowed origins list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
