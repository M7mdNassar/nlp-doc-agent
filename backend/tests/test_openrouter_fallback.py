import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.core.observability import question_scope
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import openrouter_adapter, router


def mock_http(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        openrouter_adapter.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(router.settings, "OPENROUTER_API_KEY", "test-private-key")


def completion():
    return {
        "model": "actual/free-model",
        "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    }


@pytest.mark.parametrize("limit", [3000, 4096, 6000])
def test_json_payload_reserves_output_without_reducing_reasoning_allowance(limit):
    adapter = openrouter_adapter.OpenRouterAdapter("openrouter/free")
    payload = adapter._payload("question", "system", TokenBudget(limit, json_output=True))
    assert payload["max_tokens"] == limit * 2
    assert payload["reasoning"] == {"max_tokens": limit}
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "openrouter/free"


def test_plain_text_rewriting_keeps_its_original_format_and_budget():
    payload = openrouter_adapter.OpenRouterAdapter("openrouter/free")._payload(
        "rewrite", "return plain text", TokenBudget(512)
    )
    assert payload["max_tokens"] == 512
    assert "response_format" not in payload and "reasoning" not in payload


def test_small_json_budget_does_not_send_an_unsupported_tiny_reasoning_allowance():
    payload = openrouter_adapter.OpenRouterAdapter("openrouter/free")._payload(
        "q", "s", TokenBudget(100, json_output=True)
    )
    assert payload["max_tokens"] == 100 and "reasoning" not in payload
    assert payload["response_format"] == {"type": "json_object"}


async def test_json_usage_records_the_actual_wire_ceiling_and_actual_consumption(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion())

    mock_http(monkeypatch, handler)
    with question_scope() as trace:
        result = await openrouter_adapter.OpenRouterAdapter("openrouter/free").generate_for_router(
            "q", "s", TokenBudget(3000, json_output=True)
        )
    assert result == '{"ok":true}'
    assert requests[0]["max_tokens"] == trace.requests[0].max_output_tokens == 6000
    assert trace.summary()["total_tokens"] == 25


async def test_json_mode_never_approves_or_retries_a_truncated_completion(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        data = completion()
        data["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=data)

    mock_http(monkeypatch, handler)
    with pytest.raises(LLMOutputError):
        await openrouter_adapter.OpenRouterAdapter("openrouter/free").generate_for_router(
            "q", "s", TokenBudget(3000, json_output=True)
        )
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["wall-clock", "read-timeout"])
async def test_stalled_completions_stop_without_hidden_transport_retries(monkeypatch, kind):
    calls = []

    async def handler(request):
        calls.append(request)
        if kind == "read-timeout":
            raise httpx.ReadTimeout("provider stalled", request=request)
        await asyncio.Event().wait()
        return httpx.Response(200, json=completion())

    monkeypatch.setattr(openrouter_adapter, "GENERATION_TIMEOUT_SECONDS", 0.01)
    mock_http(monkeypatch, handler)
    with question_scope() as trace, pytest.raises(LLMTimeoutError):
        await openrouter_adapter.OpenRouterAdapter("openrouter/free").generate_for_router(
            "q", "s", TokenBudget(3000, json_output=True)
        )
    assert len(calls) == 1
    assert trace.requests[0].error_type == "LLMTimeoutError"


async def test_question_cancellation_is_not_converted_to_timeout_or_retried(monkeypatch):
    entered = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request)
        entered.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=completion())

    mock_http(monkeypatch, handler)
    task = asyncio.create_task(
        openrouter_adapter.OpenRouterAdapter("openrouter/free").generate_for_router(
            "q", "s", TokenBudget(3000, json_output=True)
        )
    )
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) == 1


def setup_router(monkeypatch, groq_effect):
    groq = SimpleNamespace(
        model="groq-primary", generate_for_router=AsyncMock(side_effect=groq_effect)
    )
    monkeypatch.setattr(router, "GroqAdapter", lambda **kw: groq)
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MODELS", [])
    monkeypatch.setattr(router.settings, "OPENROUTER_FALLBACK_MODELS", ["openrouter/free"])
    return router.LLMRouter(), groq


async def test_groq_limit_uses_openrouter_immediately_under_same_logical_call(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    mock_http(monkeypatch, handler)
    llm, groq = setup_router(monkeypatch, LLMRateLimitError("Groq", 60))
    with question_scope() as trace:
        assert await llm.generate("question", "system", TokenBudget(100)) == '{"ok":true}'
    groq.generate_for_router.assert_awaited_once()
    assert trace.llm_calls == 1 and trace.waits == []
    assert trace.requests[0].provider == "openrouter"
    assert trace.requests[0].model == "actual/free-model"
    assert trace.summary()["total_tokens"] == 25
    payload = json.loads(requests[0].content)
    assert payload["model"] == "openrouter/free" and payload["max_tokens"] == 100
    assert requests[0].headers["authorization"] == "Bearer test-private-key"


async def test_groq_success_and_configuration_errors_do_not_invoke_openrouter(monkeypatch):
    mock_http(monkeypatch, lambda request: pytest.fail("OpenRouter must not be called"))
    llm, groq = setup_router(monkeypatch, None)
    groq.generate_for_router.return_value = "good"
    assert await llm.generate("q", "s", TokenBudget(10)) == "good"
    groq.generate_for_router.side_effect = LLMConfigurationError("Groq")
    with pytest.raises(LLMConfigurationError):
        await llm.generate("q", "s", TokenBudget(10))


def test_missing_key_or_empty_model_list_disables_openrouter(monkeypatch):
    monkeypatch.setattr(router.settings, "OPENROUTER_API_KEY", "")
    llm, _ = setup_router(monkeypatch, None)
    assert len(llm.providers) == 1
    monkeypatch.setattr(router.settings, "OPENROUTER_API_KEY", "present")
    monkeypatch.setattr(router.settings, "OPENROUTER_FALLBACK_MODELS", [])
    assert len(router.LLMRouter().providers) == 1


@pytest.mark.parametrize("status", [401, 402, 403, 404])
async def test_openrouter_configuration_errors_are_safe_and_not_retried(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "private-account-data"}})

    mock_http(monkeypatch, handler)
    with pytest.raises(LLMConfigurationError) as exc:
        await openrouter_adapter.OpenRouterAdapter("test").generate_for_router(
            "q", "s", TokenBudget(10)
        )
    assert len(calls) == 1
    assert "private" not in str(exc.value)


async def test_openrouter_limits_use_cooldown_and_preserve_provider_identity(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "30"}, json={"error": {"code": 429}})

    mock_http(monkeypatch, handler)
    adapter = openrouter_adapter.OpenRouterAdapter("test")
    for _ in range(2):
        with pytest.raises(LLMRateLimitError) as exc:
            await adapter.generate_for_router("q", "s", TokenBudget(10))
        assert exc.value.provider == "OpenRouter" and exc.value.retry_after_seconds == 30
    assert len(calls) == 1


async def test_stream_error_after_output_is_never_replayed(monkeypatch):
    frames = [
        {"choices": [{"delta": {"content": "partial"}, "finish_reason": None}]},
        {"error": {"code": 429, "message": "private"}},
    ]
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, text="".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)
        ),
    )
    llm, groq = setup_router(monkeypatch, None)

    async def limited(*args):
        raise LLMRateLimitError("Groq", 60)
        yield ""

    groq.stream_for_router = limited
    received = []
    with pytest.raises(LLMRateLimitError):
        async for token in llm.stream("q", "s", TokenBudget(10)):
            received.append(token)
    assert received == ["partial"]


@pytest.mark.parametrize(
    "finish,content", [("length", '{"ok":true}'), ("stop", ""), ("error", "text")]
)
async def test_incomplete_completions_are_rejected_before_analyst_parsing(
    monkeypatch, finish, content
):
    data = completion()
    data["choices"][0] = {"finish_reason": finish, "message": {"content": content}}
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=data))
    adapter = openrouter_adapter.OpenRouterAdapter("test")
    with question_scope() as trace, pytest.raises(LLMOutputError, match="incomplete") as error:
        await adapter.generate_for_router.__wrapped__(adapter, "q", "s", TokenBudget(10))
    assert error.value.finish_reason == finish
    assert trace.requests[0].total_tokens == 25


async def test_error_in_http_200_body_is_not_a_successful_completion(monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={"error": {"code": 429}}))
    with question_scope() as trace, pytest.raises(LLMRateLimitError):
        await openrouter_adapter.OpenRouterAdapter("test").generate_for_router(
            "q", "s", TokenBudget(10)
        )
    assert trace.requests[0].status_code == 429
