# Product Specification — TeleMind Hub

## 1. Overview
- **Product:** A local-first Windows desktop AI hub (**`TeleMind.exe`**) integrated with a private **Personal Telegram AI Bot**.
- **Deployment Target:** Single owner running locally on Windows desktop.
- **AI Support:** Google Gemini API (including live **Google Search Grounding**, image/PDF/voice understanding) and OpenAI / OpenAI-compatible local APIs.

## 2. Core Modules
1. **Multi-Model AI Chat & Personas (`/model`, `/mode`, `/clear`)**
   - Conversation history per chat thread, customizable system personas, daily request/token caps.
   - Live Google Search Grounding for timely queries, automatic public URL context ingestion when links are pasted, safe YouTube search link fallback, and Telegram voice note comprehension.
   - Natural-language action execution for creating/searching notes, scheduling reminders, and recording/summarizing transactions.
2. **Second Brain & Reminders (`/note`, `/find`, `/remind`)**
   - Create, edit, delete, and search notes (SQLite FTS5) and manage scheduled reminders from Telegram or Desktop UI.
3. **Personal Finance (`/chi`, `/thu`, `/thongke`, `/bill`)**
   - Integer minor-unit accounting, receipt photo OCR, monthly filters, inline edit/delete, net balance summary, and CSV export.
4. **SSRF-Safe Digest & Morning Briefing (`/tomtat`, `/feed`)**
   - Summarize public URLs cleanly, subscribe/edit/read RSS feeds directly in-app, and optionally deliver a scheduled daily morning Telegram briefing.
5. **PC & Docker Remote (`/pc`, `/docker`, `/dockerlogs`)**
   - **Disabled by default.** Read-only `psutil` metrics and container logs/status guarded by container-name validation and 60-second two-step inline confirmation on Telegram.

## 3. Security Threat Model (STRIDE Summary)
- **Spoofing:** Fail-closed Telegram allowlist (`private` chat only); Desktop IPC uses ephemeral RAM session tokens.
- **Tampering / Injection:** Parameterized SQL; `shell=False` `argv` commands; HTML escaping for Telegram output and React JSX escaping for Desktop UI.
- **Information Disclosure:** Fernet secret vault; secrets never returned in plaintext; SSRF IP validation with pinned TCP sockets.
- **Denial of Service:** Daily LLM request/token caps, bounded HTTP downloads (`2 MB`), 4,096-char Telegram chunking, single-instance OS mutex.
