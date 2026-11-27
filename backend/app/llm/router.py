"""Dual-provider LLM router with daily budget guardrails, bounded retries, and fallback."""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

import httpx

from app.config import Settings
from app.db.repositories import Repository
from app.llm.base import (
    BudgetExceededError,
    LLMError,
    LLMRequest,
    LLMResponse,
    ProviderNotConfiguredError,
)
from app.llm.gemini import GeminiClient
from app.llm.openai_client import OpenAIClient


def _is_transient_error(exc: Exception) -> bool:
    """Identify transient upstream errors safe for one quick retry."""
    if isinstance(exc, httpx.TransportError):
        return True
    msg = str(exc)
    lower = msg.lower()
    if "insufficient_quota" in lower or "credit_balance_exhausted" in lower:
        return False
    return any(
        code in msg for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")
    )


def _rank_gemini_models(raw_models: list[dict[str, Any]]) -> list[str]:
    """Filter and prioritize Gemini models suitable for text/multimodal chat."""
    blocked = ("embedding", "imagen", "veo", "tts", "audio", "robotics", "computer-use", "aqa")
    candidates: list[str] = []
    for item in raw_models:
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(item.get("name", "")).removeprefix("models/").strip()
        lower = name.lower()
        if not name or any(tok in lower for tok in blocked):
            continue
        candidates.append(name)

    def _priority(name: str) -> tuple[int, int, str]:
        lower = name.lower()
        is_exp = 1 if ("exp" in lower or "preview" in lower) else 0
        is_flash = 0 if "flash" in lower else 1
        return (is_flash, is_exp, name)

    candidates.sort(key=_priority)
    return candidates[:20]


class LLMRouter:
    """Routes requests between Google Gemini and OpenAI with retries, budget caps, and fallback."""

    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=20.0)
        self._gemini = GeminiClient(self._http)
        self._openai = OpenAIClient(self._http)
        self._gemini_models_cache: tuple[float, list[str]] = (0.0, [])
        self._model_cooldowns: dict[tuple[str, str], float] = {}

    async def close(self) -> None:
        """Close owned HTTP client."""
        if self._owns_client:
            await self._http.aclose()

    async def _check_budget(self, ai_cfg: dict[str, Any]) -> None:
        usage = await self._repo.get_daily_usage()
        req_cap = int(ai_cfg.get("daily_request_cap", self._settings.daily_llm_request_cap))
        tok_cap = int(ai_cfg.get("daily_token_cap", self._settings.daily_llm_token_cap))
        if usage["requests"] >= req_cap:
            raise BudgetExceededError(f"Daily request cap reached ({usage['requests']}/{req_cap}).")
        if usage["total_tokens"] >= tok_cap:
            raise BudgetExceededError(
                f"Daily token cap reached ({usage['total_tokens']}/{tok_cap})."
            )

    async def _call_with_retry(
        self, provider: str, model: str, req: LLMRequest, ai_cfg: dict[str, Any]
    ) -> LLMResponse:
        if provider == "gemini":
            key = await self._repo.get_secret("gemini", self._settings.gemini_api_key)
            if not key:
                raise ProviderNotConfiguredError("Gemini API key is not configured.")
        elif provider == "openai":
            key = await self._repo.get_secret("openai", self._settings.openai_api_key)
            base_url = str(ai_cfg.get("openai_base_url", "https://api.openai.com/v1"))
            if not key and ("127.0.0.1" not in base_url and "localhost" not in base_url):
                raise ProviderNotConfiguredError("OpenAI API key is not configured.")
            if not key:
                key = "ollama"
        else:
            raise LLMError(f"Unsupported provider: {provider}")

        target_model = model
        now_mono = time.monotonic()
        if (
            provider == "gemini"
            and self._model_cooldowns.get((provider, model), 0.0) > now_mono
        ):
            alt_models = [
                m
                for m in await self._get_gemini_fallback_models(exclude=model)
                if self._model_cooldowns.get((provider, m), 0.0) <= now_mono
            ]
            if alt_models:
                target_model = alt_models[0]

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                if provider == "gemini":
                    return await self._gemini.generate(
                        api_key=key,
                        model=target_model,
                        messages=req.messages,
                        system_prompt=req.system_prompt,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                        use_web_search=req.use_web_search,
                    )
                base_url = str(ai_cfg.get("openai_base_url", "https://api.openai.com/v1"))
                return await self._openai.generate(
                    api_key=key,
                    model=target_model,
                    base_url=base_url,
                    messages=req.messages,
                    system_prompt=req.system_prompt,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
            except (httpx.TransportError, LLMError) as exc:
                last_exc = exc
                if not _is_transient_error(exc) or attempt == 1:
                    break
                jitter = secrets.randbelow(200) / 1000.0
                await asyncio.sleep(0.35 + jitter)

        if provider == "gemini" and last_exc is not None:
            err_msg = str(last_exc)
            if "HTTP 503" in err_msg or "HTTP 404" in err_msg:
                ttl = 600.0 if "HTTP 404" in err_msg else 180.0
                self._model_cooldowns[(provider, target_model)] = time.monotonic() + ttl
                now_fb = time.monotonic()
                alt_models = [
                    m
                    for m in await self._get_gemini_fallback_models(exclude=target_model)
                    if m != model and self._model_cooldowns.get((provider, m), 0.0) <= now_fb
                ]
                for alt in alt_models[:2]:
                    try:
                        return await self._gemini.generate(
                            api_key=key,
                            model=alt,
                            messages=req.messages,
                            system_prompt=req.system_prompt,
                            temperature=req.temperature,
                            max_tokens=req.max_tokens,
                            use_web_search=req.use_web_search,
                        )
                    except (httpx.TransportError, LLMError) as alt_exc:
                        alt_err = str(alt_exc)
                        if "HTTP 503" in alt_err or "HTTP 404" in alt_err:
                            self._model_cooldowns[(provider, alt)] = time.monotonic() + 180.0
                        last_exc = alt_exc
                        continue

        if last_exc is not None:
            raise last_exc
        raise LLMError("LLM invocation failed.")

    async def _get_gemini_fallback_models(self, exclude: str) -> list[str]:
        now = time.monotonic()
        cached_at, cached = self._gemini_models_cache
        if now - cached_at > 300.0 or not cached:
            probe = await self.test_provider("gemini")
            cached = list(probe.get("models") or [])
            if cached:
                self._gemini_models_cache = (now, cached)
        return [m for m in cached if m != exclude]

    async def test_provider(self, provider: str) -> dict[str, Any]:
        """Verify stored credentials by listing available models cleanly."""
        started = time.monotonic()
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        try:
            if provider == "gemini":
                key = await self._repo.get_secret("gemini", self._settings.gemini_api_key)
                if not key:
                    return {
                        "ok": False,
                        "provider": provider,
                        "latency_ms": 0,
                        "models": [],
                        "error": "Chưa cấu hình Gemini API Key.",
                    }
                resp = await self._http.get(
                    f"{self._gemini.BASE_URL}",
                    headers={"x-goog-api-key": key},
                )
                latency = int((time.monotonic() - started) * 1000)
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "provider": provider,
                        "latency_ms": latency,
                        "models": [],
                        "error": f"HTTP {resp.status_code}: {resp.text[:220]}",
                    }
                raw_models = resp.json().get("models") or []
                models = _rank_gemini_models(raw_models)
                return {
                    "ok": True,
                    "provider": provider,
                    "latency_ms": latency,
                    "models": models,
                    "error": "",
                }

            if provider == "openai":
                key = await self._repo.get_secret("openai", self._settings.openai_api_key)
                base_url = str(ai_cfg.get("openai_base_url", "https://api.openai.com/v1")).rstrip(
                    "/"
                )
                if not key and ("127.0.0.1" not in base_url and "localhost" not in base_url):
                    return {
                        "ok": False,
                        "provider": provider,
                        "latency_ms": 0,
                        "models": [],
                        "error": "Chưa cấu hình OpenAI API Key.",
                    }
                resp = await self._http.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {key or 'ollama'}"},
                )
                latency = int((time.monotonic() - started) * 1000)
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "provider": provider,
                        "latency_ms": latency,
                        "models": [],
                        "error": f"HTTP {resp.status_code}: {resp.text[:220]}",
                    }
                raw_models = resp.json().get("data") or []
                models = [str(m.get("id", "")) for m in raw_models if m.get("id")][:20]
                return {
                    "ok": True,
                    "provider": provider,
                    "latency_ms": latency,
                    "models": models,
                    "error": "",
                }
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            return {
                "ok": False,
                "provider": provider,
                "latency_ms": latency,
                "models": [],
                "error": str(exc)[:220],
            }

        return {
            "ok": False,
            "provider": provider,
            "latency_ms": 0,
            "models": [],
            "error": f"Provider không hỗ trợ: {provider}",
        }

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Execute LLM completion respecting budget caps, primary provider, and fallback."""
        ai_cfg: dict[str, Any] = await self._repo.get_setting("ai", {})
        await self._check_budget(ai_cfg)

        primary = (req.preferred_provider or str(ai_cfg.get("primary_provider", "gemini"))).lower()
        fallback_enabled = bool(ai_cfg.get("fallback_enabled", True))
        secondary = "openai" if primary == "gemini" else "gemini"

        gemini_model = str(ai_cfg.get("gemini_model", "gemini-3.8-flash"))
        openai_model = str(ai_cfg.get("openai_model", "gpt-6-luna"))

        order = [primary]
        if fallback_enabled and req.preferred_provider is None:
            order.append(secondary)

        errors: list[str] = []
        llm_failed = False
        for idx, prov in enumerate(order):
            model = (
                req.preferred_model
                if (idx == 0 and req.preferred_model)
                else (gemini_model if prov == "gemini" else openai_model)
            )
            try:
                res = await self._call_with_retry(prov, model, req, ai_cfg)
                await self._repo.log_usage(
                    res.provider, res.model, res.input_tokens, res.output_tokens
                )
                return res
            except ProviderNotConfiguredError as exc:
                errors.append(f"{prov}: {exc}")
                continue
            except LLMError as exc:
                errors.append(f"{prov}: {exc}")
                llm_failed = True
                if idx == len(order) - 1:
                    raise LLMError(" | ".join(errors)) from exc

        if llm_failed:
            raise LLMError(" | ".join(errors))

        raise ProviderNotConfiguredError(
            "Chưa cấu hình API Key cho Gemini hoặc OpenAI. "
            "Hãy nhập key trong TeleMind Hub → Cài đặt chung."
        )
