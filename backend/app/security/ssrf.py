"""SSRF protection for outbound web fetching (link summarization & RSS feeds)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import typing
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})


async def _resolve_verified_public_ip(hostname: str, port: int) -> str:
    """Resolve hostname synchronously-safe and ensure every returned address is public."""
    clean_host = hostname.lower().rstrip(".")
    if (
        clean_host in BLOCKED_HOSTNAMES
        or clean_host.endswith(".local")
        or clean_host.endswith(".internal")
    ):
        raise UnsafeURLError(f"Blocked internal hostname: {clean_host}")

    try:
        literal_ip = ipaddress.ip_address(clean_host)
        if not is_public_ip(literal_ip):
            raise UnsafeURLError(f"Blocked non-public IP address: {literal_ip}")
        return str(literal_ip)
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(clean_host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"DNS resolution failed for {clean_host}.") from exc

    if not infos:
        raise UnsafeURLError(f"No DNS records found for {clean_host}.")

    first_ip = ""
    for info in infos:
        raw_ip = str(info[4][0]).split("%", 1)[0]
        resolved_ip = ipaddress.ip_address(raw_ip)
        if not is_public_ip(resolved_ip):
            raise UnsafeURLError(f"Resolved IP {resolved_ip} is not publicly routable.")
        if not first_ip:
            first_ip = str(resolved_ip)
    return first_ip


class _PublicOnlyNetworkBackend(httpcore.AsyncNetworkBackend):
    """HTTPcore network backend pinning TCP connections directly to verified public IPs."""

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> httpcore.AsyncNetworkStream:
        pinned_ip = await _resolve_verified_public_ip(host, port)
        return await self._inner.connect_tcp(pinned_ip, port, *args, **kwargs)

    async def connect_unix_socket(
        self,
        path: str,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> httpcore.AsyncNetworkStream:
        raise UnsafeURLError("Unix domain sockets are not permitted.")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _PinnedStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: typing.AsyncIterable[bytes],
        on_close: typing.Callable[[], typing.Awaitable[None]],
    ) -> None:
        self._stream = stream
        self._on_close = on_close

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        await self._on_close()


class _PublicOnlyTransport(httpx.AsyncBaseTransport):
    """Custom HTTPX transport preventing DNS rebinding and proxy env hijacking."""

    def __init__(self) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            network_backend=_PublicOnlyNetworkBackend(),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        core_resp = await self._pool.handle_async_request(core_req)
        assert isinstance(core_resp.stream, typing.AsyncIterable)
        return httpx.Response(
            status_code=core_resp.status,
            headers=core_resp.headers,
            stream=_PinnedStream(core_resp.stream, core_resp.aclose),
            extensions=core_resp.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation."""


def is_public_ip(ip: IPAddress) -> bool:
    """Return True only when an IP address is globally routable."""
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url_syntax(url: str) -> str:
    """Validate URL scheme, host presence, and absence of embedded credentials."""
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs are permitted.")
    if not parsed.hostname:
        raise UnsafeURLError("URL must contain a valid hostname.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs with embedded credentials are not permitted.")

    hostname = parsed.hostname.lower().rstrip(".")
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise UnsafeURLError(f"Blocked internal hostname: {hostname}")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None and not is_public_ip(literal_ip):
        raise UnsafeURLError(f"Blocked non-public IP address: {literal_ip}")

    return candidate


async def resolve_and_validate_url(url: str) -> str:
    """Validate URL syntax and confirm all resolved DNS targets are public IPs."""
    clean_url = validate_url_syntax(url)
    parsed = urlparse(clean_url)
    hostname = parsed.hostname
    if hostname is None:
        raise UnsafeURLError("Missing hostname.")

    try:
        ipaddress.ip_address(hostname)
        return clean_url
    except ValueError:
        pass

    await _resolve_verified_public_ip(
        hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    )
    return clean_url


async def safe_fetch_text(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 10.0,
    max_bytes: int = 2 * 1024 * 1024,
    max_redirects: int = 3,
) -> tuple[str, str, str]:
    """Fetch a public HTTP(S) resource with SSRF validation on every redirect hop.

    Returns `(final_url, content_type, decoded_text)`.
    """
    current_url = await resolve_and_validate_url(url)
    owns_client = client is None
    http = client or httpx.AsyncClient(
        transport=_PublicOnlyTransport(),
        timeout=timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    )
    headers = {"User-Agent": "TeleMindPersonalBot/0.1 (+local-digest)"}

    try:
        for _ in range(max_redirects + 1):
            current_url = await resolve_and_validate_url(current_url)
            async with http.stream("GET", current_url, headers=headers) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    if not location:
                        raise UnsafeURLError("Redirect response missing Location header.")
                    current_url = urljoin(current_url, location)
                    continue

                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"Response exceeded {max_bytes} byte limit.")
                    chunks.append(chunk)

                content_type = resp.headers.get("content-type", "text/plain")
                encoding = resp.encoding or "utf-8"
                body = b"".join(chunks).decode(encoding, errors="replace")
                return current_url, content_type, body

        raise UnsafeURLError("Exceeded maximum safe redirect hops.")
    finally:
        if owns_client:
            await http.aclose()
