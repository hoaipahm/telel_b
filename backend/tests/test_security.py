"""Security regression tests: fail-closed Telegram guard, Fernet, SSRF, auth, shell safety."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from app.modules.remote import validate_container_name
from app.security.auth import AdminAuth
from app.security.crypto import SecretVault, mask_secret
from app.security.ssrf import UnsafeURLError, safe_fetch_text, validate_url_syntax
from app.security.telegram_guard import check_telegram_access


def test_telegram_guard_fail_closed_when_empty() -> None:
    res = check_telegram_access(111, "private", set())
    assert not res.allowed
    assert "not_configured" in res.reason


def test_telegram_guard_blocks_group_and_strangers() -> None:
    allowed = {999}
    assert not check_telegram_access(999, "group", allowed).allowed
    assert not check_telegram_access(888, "private", allowed).allowed
    assert not check_telegram_access(None, "private", allowed).allowed
    assert check_telegram_access(999, "private", allowed).allowed


def test_fernet_vault_roundtrip_and_tamper(tmp_path: Path) -> None:
    vault = SecretVault.from_env_or_file("", tmp_path / "master.key")
    cipher = vault.encrypt("AIzaSySecretKey12345")
    assert "AIzaSySecretKey12345" not in cipher
    assert vault.decrypt(cipher) == "AIzaSySecretKey12345"
    assert mask_secret("AIzaSySecretKey12345") == "AIza...2345"

    with pytest.raises(ValueError):
        vault.decrypt(cipher[:-4] + "XXXX")


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost:8000/api",
        "http://127.0.0.1:3000",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/admin",
        "http://192.168.1.1",
        "http://user:pass@example.com",
        "http://myprinter.local/status",
    ],
)
def test_ssrf_blocks_unsafe_urls(bad_url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_syntax(bad_url)


async def test_ssrf_blocks_redirect_to_loopback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://93.184.216.34/start":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/secret"})
        return httpx.Response(200, text="should not reach")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        with pytest.raises(UnsafeURLError):
            await safe_fetch_text("https://93.184.216.34/start", client=client)


def test_admin_auth_constant_time_and_generation(tmp_path: Path) -> None:
    token_file = tmp_path / "admin.token"
    auth = AdminAuth.from_env_or_file("", token_file)
    assert token_file.exists()
    assert auth.verify(auth.token)
    assert not auth.verify("wrong-token")
    assert not auth.verify(None)


@pytest.mark.parametrize(
    "bad_name", ["app; rm -rf /", "$(whoami)", "--privileged", "../etc", "a b"]
)
def test_container_name_rejects_injection(bad_name: str) -> None:
    with pytest.raises(ValueError):
        validate_container_name(bad_name)


def test_container_name_accepts_valid() -> None:
    assert validate_container_name("telemind-postgres.1") == "telemind-postgres.1"
