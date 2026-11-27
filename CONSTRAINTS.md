# Project Constraints — TeleMind Personal Hub

Last reviewed: 2026-11-27

## Floor (Always Enforced)
- No suppression comments added to silence errors (`@ts-ignore`, `eslint-disable`, `# noqa`, `# type: ignore`)
- No unimplemented stubs (`throw new Error("Not implemented")`, `raise NotImplementedError`, empty `catch {}` / `except: pass`)
- No skipped or deleted tests to make the suite pass
- No hardcoded secrets, API keys, or tokens in source control
- Never use `shell=True` in `subprocess` or raw string SQL concatenation
- Never loosen constraints to pass checks

## Enforced Quality Gates
| Dimension | Rule | Checked By |
|---|---|---|
| Python Lint | Zero lint errors | `ruff check backend/app backend/tests` |
| Python Types | Zero type errors | `mypy backend/app` |
| Python Tests | 100% pass, security & modules covered | `pytest backend/tests -v` |
| TypeScript Types | Zero type errors (`strict: true`) | `npm --prefix frontend exec tsc -- --noEmit` |
| Frontend Tests | 100% pass (theme engine, utils, state) | `npm --prefix frontend test` |
| Production Build | Clean Next.js production build | `npm --prefix frontend run build` |
| Security Floor | Fail-closed Telegram guard, SSRF block, Fernet secrets, `127.0.0.1` bind | `backend/tests/test_security.py` |
