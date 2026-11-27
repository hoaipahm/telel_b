"""OpenAI (and OpenAI-compatible local endpoint) REST client."""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import ChatMessage, LLMError, LLMResponse


class OpenAIClient:
    """Async REST client for OpenAI Chat Completions and compatible local endpoints."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        messages: list[ChatMessage],
        system_prompt: str = "",
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        """Invoke `/chat/completions` with bearer authentication."""
        clean_base = base_url.rstrip("/")
        url = f"{clean_base}/chat/completions"

        formatted: list[dict[str, Any]] = []
        if system_prompt.strip():
            formatted.append({"role": "system", "content": system_prompt.strip()})

        for msg in messages:
            if msg.image_base64 and msg.image_mime:
                formatted.append(
                    {
                        "role": msg.role,
                        "content": [
                            {"type": "text", "text": msg.content},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{msg.image_mime};base64,{msg.image_base64}"
                                },
                            },
                        ],
                    }
                )
            else:
                formatted.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        resp = await self._http.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise LLMError(f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("OpenAI returned no choices.")

        message_obj = choices[0].get("message") or {}
        content = message_obj.get("content", "")
        text = content.strip() if isinstance(content, str) else str(content)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider="openai",
            model=model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            raw_finish_reason=str(choices[0].get("finish_reason", "")),
        )
