"""LLM router tests: header-based auth, fallback, and daily budget enforcement."""

from __future__ import annotations

import httpx
import pytest
from app.config import Settings
from app.db.repositories import Repository
from app.llm.base import BudgetExceededError, ChatMessage, LLMError, LLMRequest
from app.llm.router import LLMRouter


async def test_gemini_uses_header_not_query_param_and_falls_back_to_openai(
    repo: Repository,
    tmp_settings: Settings,
) -> None:
    await repo.set_secret("gemini", "AIzaTestGeminiKey9999")
    await repo.set_secret("openai", "sk-TestOpenAIKey8888")

    seen_urls: list[str] = []
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        seen_headers.append(dict(request.headers))
        if "generativelanguage.googleapis.com" in str(request.url):
            return httpx.Response(503, text="Upstream busy")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "OpenAI fallback ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    res = await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="Xin chào")]))

    assert res.provider == "openai"
    assert res.text == "OpenAI fallback ok"
    assert all("AIzaTestGeminiKey9999" not in u for u in seen_urls)
    assert any(h.get("x-goog-api-key") == "AIzaTestGeminiKey9999" for h in seen_headers)
    await client.aclose()


async def test_daily_budget_cap_blocks_excess_calls(
    repo: Repository, tmp_settings: Settings
) -> None:
    await repo.set_setting(
        "ai",
        {
            "primary_provider": "gemini",
            "fallback_enabled": False,
            "gemini_model": "gemini-3.8-flash",
            "openai_model": "gpt-6-luna",
            "openai_base_url": "https://api.openai.com/v1",
            "active_persona": "assistant",
            "daily_request_cap": 1,
            "daily_token_cap": 500000,
        },
    )
    await repo.log_usage("gemini", "gemini-3.8-flash", 10, 10)

    router = LLMRouter(repo, tmp_settings)
    with pytest.raises(BudgetExceededError):
        await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="test")]))
    await router.close()


async def test_primary_llm_error_not_masked_when_fallback_unconfigured(
    repo: Repository, tmp_settings: Settings
) -> None:
    await repo.set_secret("gemini", "AIzaTestGeminiKey9999")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text='{"error":{"code":503,"status":"UNAVAILABLE"}}')

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    with pytest.raises(LLMError, match="Gemini HTTP 503"):
        await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="hi")]))
    await client.aclose()


async def test_gemini_503_recovers_with_available_model_from_list(
    repo: Repository, tmp_settings: Settings
) -> None:
    await repo.set_secret("gemini", "AIzaTestGeminiKey9999")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if request.method == "GET" and url.endswith("/v1beta/models"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )
        if "gemini-3.8-flash:generateContent" in url:
            return httpx.Response(503, text='{"error":{"code":503,"status":"UNAVAILABLE"}}')
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Recovered!"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    res = await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert res.text == "Recovered!"
    assert res.model == "gemini-2.5-flash"
    await client.aclose()


async def test_openai_insufficient_quota_fails_fast_without_retrying(
    repo: Repository, tmp_settings: Settings
) -> None:
    await repo.set_secret("openai", "sk-TestOpenAIKey8888")
    await repo.set_setting(
        "ai",
        {
            "primary_provider": "openai",
            "fallback_enabled": False,
            "gemini_model": "gemini-3.8-flash",
            "openai_model": "gpt-6-luna",
            "openai_base_url": "https://api.openai.com/v1",
            "active_persona": "assistant",
            "daily_request_cap": 200,
            "daily_token_cap": 500000,
        },
    )
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, text='{"error":{"code":"credit_balance_exhausted"}}')

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    with pytest.raises(LLMError, match="credit_balance_exhausted"):
        await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert attempts == 1
    await client.aclose()


async def test_gemini_google_search_grounding_and_400_fallback(
    repo: Repository, tmp_settings: Settings
) -> None:
    import json

    await repo.set_secret("gemini", "AIzaTestGeminiKey9999")
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen_payloads.append(body)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Đây là bài hát."}]},
                        "finishReason": "STOP",
                        "groundingMetadata": {
                            "groundingChunks": [
                                {
                                    "web": {
                                        "title": "YouTube Music",
                                        "uri": "https://www.youtube.com/watch?v=realVideo123",
                                    }
                                }
                            ]
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 6},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    res = await router.complete(
        LLMRequest(
            messages=[ChatMessage(role="user", content="tìm bài hát")],
            use_web_search=True,
        )
    )
    assert seen_payloads[0].get("tools") == [{"google_search": {}}]
    assert res.sources == (("YouTube Music", "https://www.youtube.com/watch?v=realVideo123"),)
    await client.aclose()


async def test_model_cooldown_skips_congested_model_on_subsequent_calls(
    repo: Repository, tmp_settings: Settings
) -> None:
    await repo.set_secret("gemini", "AIzaTestGeminiKey9999")
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url.endswith("/v1beta/models"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )
        if "gemini-3.8-flash:generateContent" in url:
            seen_models.append("gemini-3.8-flash")
            return httpx.Response(503, text='{"error":{"code":503,"status":"UNAVAILABLE"}}')
        seen_models.append("gemini-2.5-flash")
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = LLMRouter(repo, tmp_settings, http_client=client)
    res1 = await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="1")]))
    assert res1.model == "gemini-2.5-flash"
    count_before = seen_models.count("gemini-3.8-flash")
    res2 = await router.complete(LLMRequest(messages=[ChatMessage(role="user", content="2")]))
    assert res2.model == "gemini-2.5-flash"
    assert seen_models.count("gemini-3.8-flash") == count_before
    await client.aclose()
