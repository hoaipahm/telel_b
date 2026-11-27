# TeleMind Hub

**TeleMind Hub** is a local-first Windows desktop application (`.NET 10 WPF + Edge WebView2`) paired with a private, modular **Telegram AI Bot** powered by Python 3.12 (`FastAPI`), encrypted local storage (`SQLite FTS5 + Fernet`), and a customizable **Theme Studio** (`Next.js` static export).

No public web frontend port is exposed: the UI runs inside a native desktop host and communicates with the local loopback Python engine over an authenticated **WebView2 `PostMessage` IPC bridge** using a per-launch ephemeral session token.

---

## Features

### 1. Secure Native Desktop Host (`.NET 10 WPF + WebView2`)
- **Zero-Browser Surface:** Loads prebuilt static UI assets from `frontend/out/` over WebView2's local virtual host (`https://telemind.local`).
- **Ephemeral IPC Authentication:** Generates a random 32-byte admin token in RAM on every launch and binds FastAPI exclusively to `127.0.0.1` on an ephemeral loopback port.
- **Single-Instance & System Tray:** Prevents duplicate Telegram bot polling via an OS `Mutex`, wakes the running window on re-launch, and minimizes to the Windows System Tray so the bot continues running quietly in the background.
- **Appearance / Theme Studio:** `System` / `Light` / `Dark` modes, 9 curated presets (`Matrix`, `Monokai`, `Night Owl`, `Nord`, `Notion`, `Material`, `Lobster`, `OG`, `One`), custom hex color pickers with WCAG AA contrast checks, font/radius controls, JSON import/export, and bilingual UI (`VI` / `EN`).

### 2. Multi-Model AI Chat, Grounding & Voice
- **Dual Provider Routing:** Supports **Google Gemini API** (with live **Google Search Grounding** via `google_search`) and **OpenAI API** (including local OpenAI-compatible endpoints such as Ollama / LM Studio).
- **Resilience & Speed:** Tracks per-model cooldowns on upstream `503`/`404` responses to skip congested models automatically, fails fast on quota exhaustion, displays live `typing...` indicators, and formats Markdown cleanly to Telegram HTML.
- **Multimodal & Tool Execution:** Supports text, images, PDFs (`<= 10 MB`), Telegram voice notes (`audio/ogg`), pasted public URL ingestion, and natural-language actions (`create_note`, `search_notes`, `create_reminder`, `log_expense`, `log_income`, `finance_summary`).
- **Desktop Chat Playground:** Test prompts, inspect replies, switch personas, test API keys + live model discovery, and edit/delete messages directly inside the app.

### 3. Modular Capabilities (Independently Toggleable)
1. **Multi-Model AI Chat (`/model`, `/mode`, `/clear`):** Configurable personas (`assistant`, `coder`, `translator`, `analyst`, or custom), daily request/token caps.
2. **Second Brain & Reminders (`/note`, `/find`, `/remind`):** Full-text SQLite FTS5 note search, inline CRUD, and `APScheduler` reminders delivered to Telegram.
3. **Personal Finance Tracker (`/chi`, `/thu`, `/thongke`, `/bill`):** Exact integer accounting (`amount_minor` — no floats), receipt OCR via multimodal AI, monthly filters, inline edit/delete, and CSV export.
4. **SSRF-Hardened Link & RSS Digest (`/tomtat`, `/feed`):** Public article summarization, RSS feed reader, optional scheduled daily morning Telegram briefing, and pinned-IP DNS-rebinding defense.
5. **PC & Docker Remote (`/pc`, `/docker`, `/dockerlogs`):** **Disabled by default.** Exposes read-only `psutil` host telemetry and strict allowlisted Docker commands requiring 60-second two-step inline confirmation on Telegram, plus an audit log.

---

## Security Architecture

See [SECURITY.md](SECURITY.md) for the full threat model and security controls. Highlights:
- **Fail-Closed Telegram Guard:** Rejects every update (and all group chats) whenever `ALLOWED_TELEGRAM_USER_IDS` is empty.
- **Encrypted Key Vault:** Telegram, Gemini, and OpenAI credentials are encrypted at rest with **Fernet** (`backend/data/master.key`); API responses return masked hints only.
- **SSRF Pinning Transport:** Validates DNS resolutions against private/loopback/link-local CIDRs and pins TCP connections to verified public IPs (`trust_env=False`).
- **Command & SQL Safety:** Strictly parameterized SQLite queries and `shell=False` `argv` arrays with strict container-name regex validation.

---

## Quick Start (Windows Local Development & Build)

### Prerequisites
- **Python 3.12+**
- **Node.js 20+** and `npm`
- **.NET 10 SDK** (`net10.0-windows`) & Microsoft Edge WebView2 Runtime

### 1. Backend Setup
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"
```

### 2. Frontend Static Export
```powershell
cd frontend
npm ci
npm run build
```

### 3. Build Desktop Executable (`TeleMind.exe`)
> **Note:** On paths containing spaces or apostrophes, publish to `%TEMP%` first and copy to `desktop\publish\`.

```powershell
$pub = Join-Path $env:TEMP "telemind_pub"
dotnet publish desktop\TeleMind.Desktop.csproj -c Release -r win-x64 --no-self-contained -p:PublishSingleFile=true -o $pub
Copy-Item "$pub\*" "desktop\publish\" -Recurse -Force
```

### 4. Launch & Configure
1. Run `desktop\publish\TeleMind.exe`.
2. Open **General Settings** inside the app:
   - Save your **Telegram Bot Token** (from `@BotFather`).
   - Save your **Google Gemini API Key** and/or **OpenAI API Key** (click **Test & Fetch Models** to verify).
   - Enter your numeric **Telegram User ID** (from `@userinfobot`) in **Allowed Telegram User IDs**, then click **Save Configuration**.
3. Click **Reload Telegram Bot** and send `/start` to your bot on Telegram.

---

## Verification & Quality Gates

All checks defined in [CONSTRAINTS.md](CONSTRAINTS.md) can be run locally:

```powershell
# Backend lint, strict type-checking, and test suite
Push-Location backend
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\mypy.exe app
.\.venv\Scripts\pytest.exe tests -v
Pop-Location

# Frontend type-checking, unit tests, and production static build
Push-Location frontend
.\node_modules\.bin\tsc.cmd --noEmit
npm test
npm run build
Pop-Location
```

---

## Project Structure

```text
├── backend/                 # Python 3.12 FastAPI control plane, Telegram bot & SQLite FTS5
│   ├── app/
│   │   ├── api/             # Authenticated REST routes (/api/v1/*)
│   │   ├── bot/             # Telegram polling handlers, HTML formatting, typing indicator
│   │   ├── db/              # Async SQLite schema, migrations & parameterized repositories
│   │   ├── llm/             # Gemini (with google_search + audio) & OpenAI router w/ cooldowns
│   │   ├── modules/         # Chat, Second Brain, Finance, Digest, Safe Remote
│   │   └── security/        # Fernet vault, SSRF IP-pinned transport, Telegram guard, Auth
│   └── tests/               # Pytest unit & integration suite
├── frontend/                # Next.js 15 + Tailwind CSS v4 + Theme Studio (static export)
│   ├── src/
│   └── tests/
├── desktop/                 # .NET 10 WPF + Edge WebView2 host, single-instance Mutex & Tray
├── docs/                    # Architecture decisions & product specification
├── SECURITY.md              # Threat model, hardening guarantees & secret hygiene policy
└── CONSTRAINTS.md           # Enforced quality bar & security gates
```

---

## License

For personal/self-hosted use. Review dependencies and API terms for Google Gemini, OpenAI, and Telegram before redistribution.
