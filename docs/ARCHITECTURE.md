# Architecture & Decisions — TeleMind Hub

## System Overview

```text
┌──────────────────────────────┐        ┌───────────────────────────────────────────┐
│ TeleMind Desktop (.exe)      │        │ Local Python 3.12 Engine (FastAPI)        │
│ (.NET 10 WPF + Edge WebView2)│◄──────►│  ├─ Security (Guard / Fernet / Pin-SSRF)  │
│  ├─ Next.js Static UI (out/) │ PostMsg│  ├─ Telegram Polling Bot + APScheduler    │
│  ├─ Single-Instance Mutex    │  IPC   │  ├─ Chat + Tool Actions + Audio/PDF/Image │
│  └─ Windows System Tray      │        │  ├─ LLM Router (Gemini Search / OpenAI)   │
└──────────────────────────────┘        │  └─ SQLite (WAL + FTS5 + Audit + Usage)   │
                                        └─────────────────────┬─────────────────────┘
                                                              │ Long Polling (Private Only)
                                        ┌─────────────────────▼─────────────────────┐
                                        │ Telegram Bot API (Authorized Owner IDs)   │
                                        └───────────────────────────────────────────┘
```

## Architecture Decision Records (ADRs)

- **ADR-001 (WPF + WebView2 Desktop Host):** Replaces a public localhost browser UI with a signed/local static bundle inside `WebView2`, avoiding cross-origin exposure, browser extension tampering, and forgotten terminal windows while adding OS-native single-instance locking and System Tray background execution.
- **ADR-002 (SQLite WAL + FTS5):** Zero-dependency embedded storage on Windows with ACID writes, full-text search via `notes_fts`, and integer-only financial accounting (`amount_minor`).
- **ADR-003 (Direct `httpx` REST LLM Adapters + Cooldown Routing):** Direct REST clients for Gemini (`x-goog-api-key`, `google_search` grounding, image/audio `inlineData`) and OpenAI/local endpoints prevent heavy SDK bloat, track upstream `503`/`404` cooldowns cleanly, and enable deterministic `MockTransport` unit tests.
- **ADR-004 (Pinned-IP `httpcore` Backend for SSRF):** Custom `AsyncNetworkBackend` validates public IPs prior to TCP `connect_tcp` and disables environment proxy inheritance (`trust_env=False`), closing DNS rebinding windows.
- **ADR-005 (CSS Variable Two-Layer Theme Engine):** All theme presets and live hex overrides resolve to semantic CSS custom properties (`--bg`, `--fg`, `--accent`, `--surface`, `--surface-elevated`, `--border`, `--muted`, `--radius-base`) persisted in both `localStorage` and SQLite.

## Database Schema (Core Tables)

- `settings` (`key`, `value_json`, `updated_at`) — Stores `modules`, `ai`, `personas`, `theme`, `briefing`, `allowed_telegram_user_ids`
- `secrets` (`provider`, `encrypted_value`, `hint`, `updated_at`) — Fernet-encrypted `telegram`, `gemini`, `openai` credentials
- `conversations` (`id`, `chat_id`, `role`, `content`, `provider`, `model`, `tokens_used`, `created_at`)
- `notes` + `notes_fts` — Second Brain entries synchronized via SQLite FTS5 triggers (`notes_ai`, `notes_ad`, `notes_au`)
- `reminders` — Scheduled Telegram alerts dispatched by `APScheduler`
- `transactions` — Exact integer accounting (`amount_minor > 0`, `expense`/`income`)
- `digests` & `feeds` — Saved article summaries and RSS feed subscriptions
- `audit_logs` & `usage_logs` — Security audit events and daily LLM quota accounting
