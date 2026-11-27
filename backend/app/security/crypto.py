"""Symmetric encryption at rest for user-configured API keys and tokens."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def mask_secret(secret: str) -> str:
    """Return a non-sensitive masked preview of a secret string."""
    stripped = secret.strip()
    if not stripped:
        return ""
    if len(stripped) <= 8:
        return "*" * len(stripped)
    return f"{stripped[:4]}...{stripped[-4:]}"


class SecretVault:
    """Fernet-backed vault for encrypting and decrypting secrets stored in SQLite."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_env_or_file(cls, env_key: str, key_file: Path) -> SecretVault:
        """Load Fernet key from environment or create/load a local key file."""
        raw_key = env_key.strip()
        if raw_key:
            return cls(Fernet(raw_key.encode("utf-8")))

        key_file.parent.mkdir(parents=True, exist_ok=True)
        if key_file.exists():
            stored = key_file.read_text(encoding="utf-8").strip()
            return cls(Fernet(stored.encode("utf-8")))

        generated = Fernet.generate_key()
        key_file.write_text(generated.decode("utf-8"), encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return cls(Fernet(generated))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext secret into a UTF-8 Fernet token."""
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token back into plaintext, raising ValueError on tampering."""
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt stored secret with current master key.") from exc
