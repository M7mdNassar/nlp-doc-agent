"""OpenRouter fallback with safe diagnostics and no hidden SDK retries."""

import asyncio
import json
import math
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.core.config import settings
from src.core.observability import ProviderRequest, provider_request
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMCooldownError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.domain.value_objects.token_budget import TokenBudget

from .retry import async_retry
from .usage import record_response

URL = "https://openrouter.ai/api/v1/chat/completions"
GENERATION_TIMEOUT_SECONDS = 60


class OpenRouterAdapter:
    def __init__(self, model: str) -> None:
        self.model = model
        self._rate_limit_until = 0.0

    def _check_rate_limit(self) -> None:
        remaining = self._rate_limit_until - time.monotonic()
        if remaining > 0:
            raise LLMCooldownError("OpenRouter", math.ceil(remaining))

    def _error(self, status: int, headers: httpx.Headers) -> LLMProviderError:
        if status == 429:
            seconds = None
            try:
                delay = float(headers.get("retry-after", ""))
                if math.isfinite(delay) and delay > 0:
                    seconds = math.ceil(delay)
            except ValueError:
                pass
            if seconds is not None:
                self._rate_limit_until = max(self._rate_limit_until, time.monotonic() + seconds)
            return LLMRateLimitError("OpenRouter", seconds)
        if status in {400, 401, 402, 403, 404, 413, 422}:
            return LLMConfigurationError("OpenRouter")
        return LLMProviderError("OpenRouter")

    def _payload(self, prompt: str, system: str, budget: TokenBudget) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": budget.remaining,
        }
        if budget.json_output:
            payload["response_format"] = {"type": "json_object"}
            if budget.remaining >= 1024:
                # OpenRouter counts thinking and the JSON response in the same
                # limit. Keep the old thinking allowance and reserve as much
                # room for the actual response; never disable review/reasoning.
                payload["reasoning"] = {"max_tokens": budget.remaining}
                payload["max_tokens"] = budget.remaining * 2
        return payload

    def _record_data(
        self, record: ProviderRequest, data: dict[str, Any], headers: httpx.Headers
    ) -> None:
        if data.get("error"):
            code = data["error"].get("code", 502)
            status = int(code) if str(code).isdigit() else 502
            record.status_code = status
            raise self._error(status, headers)
        record_response(record, data)
        if isinstance(data.get("model"), str):
            record.model = data["model"]

    @async_retry(max_retries=3, max_rate_limit_wait=0)
    async def generate_for_router(self, prompt: str, system: str, budget: TokenBudget) -> str:
        self._check_rate_limit()
        payload = self._payload(prompt, system, budget)
        with provider_request("openrouter", self.model, payload["max_tokens"]) as record:
            try:
                async with (
                    asyncio.timeout(GENERATION_TIMEOUT_SECONDS),
                    httpx.AsyncClient(timeout=90) as client,
                ):
                    response = await client.post(
                        URL,
                        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                        json=payload,
                    )
                record.status_code = response.status_code
                record.provider_request_id = response.headers.get("x-request-id")
                if response.status_code >= 400:
                    raise self._error(response.status_code, response.headers)
                data = response.json()
                self._record_data(record, data, response.headers)
                choices = data.get("choices") or []
                choice = choices[0] if choices else {}
                record.finish_reason = choice.get("finish_reason")
                content = (choice.get("message") or {}).get("content")
                if (
                    record.finish_reason != "stop"
                    or not isinstance(content, str)
                    or not content.strip()
                ):
                    raise LLMOutputError("OpenRouter", finish_reason=record.finish_reason)
                return content
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise LLMTimeoutError("OpenRouter") from exc
            except httpx.HTTPError as exc:
                raise LLMProviderError("OpenRouter") from exc

    async def stream_for_router(
        self, prompt: str, system: str, budget: TokenBudget
    ) -> AsyncGenerator[str, None]:
        self._check_rate_limit()
        payload = self._payload(prompt, system, budget)
        with provider_request("openrouter", self.model, payload["max_tokens"]) as record:
            try:
                async with (
                    httpx.AsyncClient(timeout=90) as client,
                    client.stream(
                        "POST",
                        URL,
                        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                        json={
                            **payload,
                            "stream": True,
                            "stream_options": {"include_usage": True},
                        },
                    ) as response,
                ):
                    record.status_code = response.status_code
                    if response.status_code >= 400:
                        raise self._error(response.status_code, response.headers)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        data = json.loads(raw)
                        self._record_data(record, data, response.headers)
                        for choice in data.get("choices", []):
                            record.finish_reason = (
                                choice.get("finish_reason") or record.finish_reason
                            )
                            content = (choice.get("delta") or {}).get("content")
                            if isinstance(content, str) and content:
                                yield content
                    if record.finish_reason != "stop":
                        raise LLMProviderError("OpenRouter")
            except httpx.HTTPError as exc:
                raise LLMProviderError("OpenRouter") from exc
