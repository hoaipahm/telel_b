"""Local Web Control Panel authentication token management."""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path


class AdminAuth:
    """Constant-time bearer token verifier for the local control plane."""

    def __init__(self, token: str) -> None:
        self._token = token

    @classmethod
    def from_env_or_file(cls, env_token: str, token_file: Path) -> AdminAuth:
        """Load admin token from env or generate and persist one locally."""
        clean = env_token.strip()
        if clean:
            return cls(clean)

        token_file.parent.mkdir(parents=True, exist_ok=True)
        if token_file.exists():
            stored = token_file.read_text(encoding="utf-8").strip()
            if stored:
                return cls(stored)

        generated = secrets.token_urlsafe(32)
        token_file.write_text(generated, encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass
        return cls(generated)

    @property
    def token(self) -> str:
        """Current admin bearer token."""
        return self._token

    def verify(self, candidate: str | None) -> bool:
        """Verify candidate bearer token using constant-time comparison."""
        if not candidate:
            return False
        return hmac.compare_digest(self._token, candidate.strip())
