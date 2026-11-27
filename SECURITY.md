# Security Policy & Threat Model — TeleMind Hub

TeleMind Hub handles personal notes, financial ledgers, Telegram credentials, and LLM API keys locally on the user's machine. Security defaults are **fail-closed**.

## Implemented Security Controls

1. **Zero-Browser Exposure & Ephemeral IPC Token**
   - The UI loads statically inside `.NET 10 WPF + Edge WebView2` (`https://telemind.local` with `DenyCors`), never over a browser-accessible LAN port.
   - Each desktop launch generates a fresh 32-byte session token in RAM and spawns FastAPI strictly on `127.0.0.1` on an ephemeral port.
   - All REST calls tunnel through `WebView2.PostWebMessageAsJson` in C#; the admin bearer token is never stored in browser `localStorage` or JS globals.

2. **Fail-Closed Telegram Authorization**
   - Every incoming update (`message`, `callback_query`) validates `chat.type == "private"` and checks `user.id` against `ALLOWED_TELEGRAM_USER_IDS`.
   - If the allowlist is empty, all updates are rejected (`backend/app/security/telegram_guard.py`).

3. **Secrets Encrypted at Rest**
   - API keys and tokens entered through Settings are encrypted with **Fernet** symmetric encryption (`cryptography.fernet`) using a locally generated key (`backend/data/master.key`).
   - Plaintext secrets are never returned by any REST endpoint or written to audit logs; only masked 4-char prefix/suffix hints are exposed.

4. **SSRF & DNS Rebinding Protection**
   - Link summarization, chat URL ingestion, and RSS fetches validate URL scheme (`http`/`https`), disallow embedded credentials, block internal hostnames (`.local`, `.internal`, `localhost`, metadata IPs), verify all resolved DNS IPs are globally routable, enforce bounded redirects/size limits (`2 MB`), and pin TCP socket connections in `httpcore` directly to the validated public IP (`trust_env=False`).

5. **Safe Process Execution & Parameterized SQL**
   - Docker/host remote probes are disabled by default (`modules.remote = false`).
   - Enabled Docker log inspection enforces a strict container-name regex (`^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$`), fixed `argv` lists with `shell=False`, and 60-second single-use Telegram inline confirmation tokens tied to the requesting user ID.
   - Database queries use strictly parameterized `aiosqlite` bindings (`?`) and database-level `CHECK` constraints (`amount_minor > 0`, integer VND/minor units).

## Repository Hygiene Rules

- Never commit `.env`, `backend/data/`, `*.db*`, `*.key`, `*.token`, `*.lnk`, or compiled executables.
- Always run `backend/tests/test_security.py` and verify staged diffs before pushing changes.
