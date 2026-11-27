"""Google Gemini REST API client using x-goog-api-key header authentication."""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import ChatMessage, LLMError, LLMResponse


class GeminiClient:
    """Async REST client for Google Gemini `generateContent` endpoint."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[ChatMessage],
        system_prompt: str = "",
        temperature: float = 0.4,
        max_tokens: int = 1200,
        use_web_search: bool = False,
    ) -> LLMResponse:
        """Invoke Gemini `generateContent` cleanly without placing API keys in URLs."""
        url = f"{self.BASE_URL}/{model}:generateContent"
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            parts: list[dict[str, Any]] = [{"text": msg.content}]
            if msg.image_base64 and msg.image_mime:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": msg.image_mime,
                            "data": msg.image_base64,
                        }
                    }
                )
            if msg.audio_base64 and msg.audio_mime:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": msg.audio_mime,
                            "data": msg.audio_base64,
                        }
                    }
                )
            contents.append({"role": role, "parts": parts})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_prompt.strip()}]}
        if use_web_search:
            payload["tools"] = [{"google_search": {}}]

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        resp = await self._http.post(url, headers=headers, json=payload)
        if (
            resp.status_code == 400
            and use_web_search
            and any(k in resp.text.lower() for k in ("google_search", "tool", "search"))
        ):
            payload.pop("tools", None)
            resp = await self._http.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            raise LLMError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("Gemini returned no candidates.")

        parts_out = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(p.get("text", "")) for p in parts_out).strip()

        sources: list[tuple[str, str]] = []
        seen_uris: set[str] = set()
        grounding = candidates[0].get("groundingMetadata") or {}
        for chunk in grounding.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            uri = str(web.get("uri") or "").strip()
            title = str(web.get("title") or uri).strip()
            if uri.startswith(("https://", "http://")) and uri not in seen_uris:
                seen_uris.add(uri)
                sources.append((title[:80], uri))

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider="gemini",
            model=model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            raw_finish_reason=str(candidates[0].get("finishReason", "")),
            sources=tuple(sources[:5]),
        )
