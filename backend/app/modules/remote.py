"""Safe PC & Docker Remote module: read-only probes and 2-step signed confirmation presets."""

from __future__ import annotations

import asyncio
import json
import platform
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from typing import Any

import psutil

from app.db.repositories import Repository

CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")

ALLOWED_PRESETS: dict[str, tuple[str, list[str]]] = {
    "docker_ps": (
        "Xem danh sách container Docker đang chạy",
        ["docker", "ps", "-a", "--format", "{{json .}}"],
    ),
    "docker_version": (
        "Kiểm tra phiên bản Docker Engine",
        ["docker", "version", "--format", "{{.Server.Version}}"],
    ),
}


@dataclass
class PendingConfirmation:
    """Single-use signed confirmation token with short expiration."""

    token: str
    user_id: int
    preset_id: str
    arg: str
    expires_at: float


def validate_container_name(name: str) -> str:
    """Validate Docker container name strictly to prevent flag/argument injection."""
    clean = name.strip()
    if not CONTAINER_NAME_RE.match(clean):
        raise ValueError("Tên container không hợp lệ (chỉ cho phép chữ, số, `_`, `.`, `-`).")
    return clean


async def run_safe_argv(argv: list[str], timeout_seconds: float = 10.0) -> tuple[int, str]:
    """Execute a fixed argv array with `shell=False` and bounded timeout."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"Command timed out after {timeout_seconds}s") from None

    out = stdout_b.decode("utf-8", errors="replace").strip()
    err = stderr_b.decode("utf-8", errors="replace").strip()
    combined = out if out else err
    return int(proc.returncode or 0), combined[:3500]


class RemoteService:
    """Host telemetry & allowlisted Docker helper with mandatory 2-step confirmation."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo
        self._pending: dict[str, PendingConfirmation] = {}

    def get_host_stats(self) -> dict[str, Any]:
        """Collect read-only host CPU, RAM, and disk metrics safely via psutil."""
        vm = psutil.virtual_memory()
        disk = shutil.disk_usage(".")
        return {
            "platform": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_used_gb": round(vm.used / (1024**3), 2),
            "ram_total_gb": round(vm.total / (1024**3), 2),
            "ram_percent": vm.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
        }

    async def list_docker_containers(self) -> list[dict[str, str]]:
        """Run `docker ps` without shell interpolation and parse JSON lines."""
        try:
            code, output = await run_safe_argv(
                ["docker", "ps", "-a", "--format", "{{json .}}"], timeout_seconds=8.0
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Docker CLI không khả dụng trong môi trường này.") from exc
        if code != 0:
            raise RuntimeError(output or "Không thể truy vấn Docker daemon.")
        items: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            items.append(
                {
                    "id": str(raw.get("ID", "")),
                    "names": str(raw.get("Names", "")),
                    "image": str(raw.get("Image", "")),
                    "status": str(raw.get("Status", "")),
                    "state": str(raw.get("State", "")),
                }
            )
        return items

    async def read_docker_logs(self, container_name: str, tail: int = 40) -> str:
        """Read bounded logs of a validated container name."""
        safe_name = validate_container_name(container_name)
        safe_tail = str(max(1, min(tail, 100)))
        code, output = await run_safe_argv(
            ["docker", "logs", "--tail", safe_tail, safe_name], timeout_seconds=8.0
        )
        if code != 0:
            raise RuntimeError(output or f"Không đọc được log container {safe_name}.")
        return output

    def request_confirmation(
        self, user_id: int, preset_id: str, arg: str = ""
    ) -> PendingConfirmation:
        """Issue a single-use 60-second confirmation token for a preset action."""
        self._prune_expired()
        if preset_id not in ALLOWED_PRESETS and preset_id != "docker_logs":
            raise ValueError(f"Preset không nằm trong whitelist: {preset_id}")
        if preset_id == "docker_logs":
            arg = validate_container_name(arg)

        token = secrets.token_urlsafe(12)
        pending = PendingConfirmation(
            token=token,
            user_id=user_id,
            preset_id=preset_id,
            arg=arg,
            expires_at=time.monotonic() + 60.0,
        )
        self._pending[token] = pending
        return pending

    async def confirm_and_execute(self, token: str, user_id: int) -> str:
        """Verify ownership and expiry, consume token atomically, and execute preset."""
        self._prune_expired()
        pending = self._pending.get(token)
        if pending is None:
            await self._repo.log_audit(
                f"tg:{user_id}", "remote_confirm", "rejected", "expired_or_missing_token"
            )
            raise ValueError("Yêu cầu đã hết hạn hoặc đã được xử lý.")
        if pending.user_id != user_id:
            await self._repo.log_audit(f"tg:{user_id}", "remote_confirm", "denied", "user_mismatch")
            raise PermissionError("Bạn không có quyền xác nhận thao tác này.")
        self._pending.pop(token, None)

        if pending.preset_id == "docker_logs":
            result = await self.read_docker_logs(pending.arg)
        else:
            _, argv = ALLOWED_PRESETS[pending.preset_id]
            code, output = await run_safe_argv(argv)
            if code != 0:
                await self._repo.log_audit(
                    f"tg:{user_id}", f"remote:{pending.preset_id}", "error", output[:200]
                )
                raise RuntimeError(output or "Lệnh thất bại.")
            result = output

        await self._repo.log_audit(
            f"tg:{user_id}", f"remote:{pending.preset_id}", "executed", pending.arg
        )
        return result or "(Không có output)"

    def cancel_confirmation(self, token: str, user_id: int) -> bool:
        pending = self._pending.get(token)
        if pending is None or pending.user_id != user_id:
            return False
        self._pending.pop(token, None)
        return True

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._pending.items() if v.expires_at < now]
        for k in expired:
            self._pending.pop(k, None)
