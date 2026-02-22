"""Async Gemini API client using httpx with OpenAI-compatible /chat/completions."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("agentswarm.gemini")


@dataclass
class LLMMessage:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    latency_ms: int


class GeminiClient:
    """Async client for Gemini's OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_s: float = 300.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=30.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

        self.total_requests = 0
        self.total_tokens_used = 0

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Send a chat completion request and return the parsed response."""
        url = f"{self.endpoint}/chat/completions"
        start_ms = time.time() * 1000
        self.total_requests += 1

        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        logger.debug(
            "LLM request → %s (model=%s, msgs=%d, chars=%d)",
            url,
            payload["model"],
            len(messages),
            sum(len(m.content) for m in messages),
        )

        resp = await self._client.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        if resp.status_code == 429:
            # Rate limited — let caller handle retry/backoff.
            raise RateLimitError(f"Gemini rate limit (429): {resp.text[:500]}")

        if resp.status_code != 200:
            raise APIError(
                f"Gemini API error ({resp.status_code}): {resp.text[:1000]}"
            )

        raw = resp.json()
        latency_ms = int(time.time() * 1000 - start_ms)

        # Gemini sometimes wraps the response in a JSON array.
        data = raw[0] if isinstance(raw, list) else raw

        # Check for API error embedded in the response body.
        if "error" in data and "choices" not in data:
            err = data["error"]
            code = err.get("code", 0)
            msg = err.get("message", str(err))
            if code == 429:
                raise RateLimitError(f"Gemini rate limit: {msg[:500]}")
            raise APIError(f"Gemini API error ({code}): {msg[:1000]}")

        usage = data.get("usage", {})
        total = usage.get("total_tokens", 0)
        self.total_tokens_used += total

        # Extract content — handle both standard and nested formats.
        choice = data["choices"][0]
        message = choice.get("message", {})
        content = message.get("content") or message.get("text", "")

        if not content:
            raise APIError(f"Empty content in Gemini response: {str(data)[:500]}")

        logger.debug(
            "LLM response ← %d chars, %d tokens, %dms, finish=%s",
            len(content),
            total,
            latency_ms,
            choice.get("finish_reason", "?"),
        )

        return LLMResponse(
            content=content,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=total,
            finish_reason=choice.get("finish_reason", "unknown"),
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        await self._client.aclose()


class RateLimitError(Exception):
    """Raised when the API returns 429."""


class APIError(Exception):
    """Raised on non-200/non-429 API responses."""
