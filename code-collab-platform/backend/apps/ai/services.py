"""Provider-agnostic AI adapter with secret stripping."""

from __future__ import annotations

import os
import re
from typing import Protocol

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
    r"(?i)(password|secret|token|key)\s*[:=]\s*[^\s\n]{4,}",
    r"-----BEGIN [A-Z ]+-----",
    r"[A-Za-z0-9+/]{40,}={0,2}",
]

SECRET_COMPILED = [re.compile(pattern) for pattern in SECRET_PATTERNS]

_PROVIDER_INSTANCE = None


class AIProvider(Protocol):
    async def complete(self, messages: list, max_tokens: int) -> str: ...


def _ai_settings() -> dict:
    try:
        from django.conf import settings

        return {
            "provider": settings.AI_PROVIDER,
            "openai_api_key": settings.OPENAI_API_KEY,
            "anthropic_api_key": getattr(settings, "ANTHROPIC_API_KEY", ""),
            "openai_model": getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic_model": getattr(settings, "ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
        }
    except Exception:
        return {
            "provider": os.environ.get("AI_PROVIDER", "openai"),
            "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
            "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic_model": os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
        }


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import openai

        config = _ai_settings()
        self.client = openai.AsyncOpenAI(api_key=api_key or config["openai_api_key"])
        self.model = model or config["openai_model"]

    async def complete(self, messages: list, max_tokens: int = 500) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import anthropic

        config = _ai_settings()
        self.client = anthropic.AsyncAnthropic(api_key=api_key or config["anthropic_api_key"])
        self.model = model or config["anthropic_model"]

    async def complete(self, messages: list, max_tokens: int = 500) -> str:
        system = next(
            (message["content"] for message in messages if message["role"] == "system"), ""
        )
        user_messages = [message for message in messages if message["role"] != "system"]
        response = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=user_messages,
            max_tokens=max_tokens,
        )
        return response.content[0].text


def get_provider() -> AIProvider:
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is None:
        provider_name = _ai_settings()["provider"]
        if provider_name == "openai":
            _PROVIDER_INSTANCE = OpenAIProvider()
        elif provider_name == "anthropic":
            _PROVIDER_INSTANCE = AnthropicProvider()
        else:
            raise ValueError(f"Unknown AI provider: {provider_name}")
    return _PROVIDER_INSTANCE


def reset_provider_cache() -> None:
    global _PROVIDER_INSTANCE
    _PROVIDER_INSTANCE = None


def strip_secrets(text: str) -> str:
    """Remove potential secrets from code before sending to AI provider."""
    for pattern in SECRET_COMPILED:
        text = pattern.sub("[REDACTED]", text)
    return text


# SECURITY AUDIT: strip_secrets() is invoked in views/tasks immediately before every provider call.
