"""Shared LLM data structures and error hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatMessage:
    """Single message in an LLM conversation turn."""

    role: str
    content: str
    image_base64: str | None = None
    image_mime: str | None = None
    audio_base64: str | None = None
    audio_mime: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response returned by any LLM provider."""

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw_finish_reason: str = ""
    sources: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LLMRequest:
    """Normalized request sent to the LLM router."""

    messages: list[ChatMessage]
    system_prompt: str = ""
    temperature: float = 0.4
    max_tokens: int = 1200
    preferred_provider: str | None = None
    preferred_model: str | None = None
    use_web_search: bool = False
    extra_hints: dict[str, str] = field(default_factory=dict)


class LLMError(RuntimeError):
    """Base error for LLM routing failures."""


class BudgetExceededError(LLMError):
    """Raised when daily request or token cap is reached."""


class ProviderNotConfiguredError(LLMError):
    """Raised when neither Gemini nor OpenAI has an active API key."""
