# Implementation Plan — TeleMind Hub

## Vertical Slices & Checkpoints
1. **Slice 1 — Security, Config & Database Core**
   - Fernet secret vault, Fail-closed Telegram guard, SSRF pinned-IP validator (`trust_env=False`), constant-time Admin token auth, Async SQLite + WAL + FTS5 + migrations.
   - Verified with `pytest backend/tests/test_security.py backend/tests/test_database.py`.
2. **Slice 2 — Dual LLM Router & Modular Capabilities**
   - Gemini (`google_search` grounding, multimodal image/audio `inlineData`) + OpenAI REST adapters, per-model cooldown cache, fast quota fail-fast, daily budget caps.
   - Natural-language tool actions (`chat`), Second Brain + `APScheduler` reminders (`brain`), exact integer Finance + CSV (`finance`), SSRF-safe Link/RSS Digest + Morning Briefing (`digest`), Safe PC/Docker Remote + 60s 2FA confirmations (`remote`).
   - Verified with `pytest backend/tests/test_llm_router.py backend/tests/test_modules.py`.
3. **Slice 3 — FastAPI Control Plane & Telegram Bot Runner**
   - Uniform REST API (`/health`, `/ready`, `/api/v1/*`), concurrent Telegram polling, HTML formatting fallback, live typing indicator, and full CRUD endpoints.
   - Verified with `pytest backend/tests/test_api.py`, `ruff`, `mypy`.
4. **Slice 4 — Next.js Control Panel & Theme Studio**
   - Obsidian sidebar layout, Appearance Theme Studio (`System`/`Light`/`Dark`, 9 presets, Accent/Background/Foreground hex pickers, WCAG AA contrast ratio, Reset/Import/Export), clickable Markdown/link chat playground, and inline CRUD across all operational panels.
   - Verified with `tsc --noEmit`, `vitest`, `next build`.
5. **Slice 5 — Native Windows Desktop Host (`TeleMind.exe`)**
   - `.NET 10 WPF + Edge WebView2` virtual-host container (`https://telemind.local`), ephemeral RAM IPC bearer auth, single-instance OS Mutex/wake signal, and Windows System Tray background runtime.
   - Verified with `dotnet publish`.
