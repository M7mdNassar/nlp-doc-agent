from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from groq import APIConnectionError, AuthenticationError, RateLimitError

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.agents.retriever.query_rewriter import QueryRewriter
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.domain.entities.evidence import EvidencePackage
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
)
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import groq_adapter, retry, router


def rate_error(header="878.688"):
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        headers={"retry-after": header} if header is not None else {},
    )
    return RateLimitError("Private provider/account detail", response=response, body=None)


def adapter_with(monkeypatch, effects):
    create = AsyncMock(side_effect=effects)
    constructor = Mock(
        return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    monkeypatch.setattr(groq_adapter, "AsyncGroq", constructor)
    sleep = AsyncMock()
    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    adapter = groq_adapter.GroqAdapter()
    assert constructor.call_args.kwargs["max_retries"] == 0
    return adapter, create, sleep


async def test_rate_limit_is_not_retried_and_cooldown_expires(monkeypatch):
    completed = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content="valid completion")
            )
        ]
    )
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error(), completed])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    with pytest.raises(LLMRateLimitError) as initial:
        await adapter.generate("q", "s", TokenBudget(100))
    assert initial.value.retry_after_seconds == 879
    assert "Private" not in str(initial.value)
    clock[0] += 30
    with pytest.raises(LLMRateLimitError) as cached:
        await adapter.generate("q", "s", TokenBudget(100))
    assert cached.value.retry_after_seconds == 849
    create.assert_awaited_once()
    sleep.assert_not_awaited()
    clock[0] += 850
    assert await adapter.generate("q", "s", TokenBudget(100)) == "valid completion"
    assert create.await_count == 2


@pytest.mark.parametrize("header", [None, "invalid", "NaN", "inf", "-1"])
async def test_invalid_rate_limit_headers_do_not_invent_a_reset_time(monkeypatch, header):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error(header)])
    with pytest.raises(LLMRateLimitError) as error:
        await adapter.generate("q", "s", TokenBudget(100))
    assert error.value.retry_after_seconds is None
    create.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_authentication_errors_are_safe_and_not_retried(monkeypatch):
    response = httpx.Response(401, request=httpx.Request("POST", "https://provider.test"))
    failure = AuthenticationError("Private credential detail", response=response, body=None)
    adapter, create, sleep = adapter_with(monkeypatch, [failure])
    with pytest.raises(LLMConfigurationError) as error:
        await adapter.generate("q", "s", TokenBudget(100))
    assert "Private" not in str(error.value)
    create.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_transient_connection_errors_keep_one_bounded_retry_layer(monkeypatch):
    failure = APIConnectionError(request=httpx.Request("POST", "https://provider.test"))
    adapter, create, sleep = adapter_with(monkeypatch, [failure] * 3)
    with pytest.raises(LLMProviderError):
        await adapter.generate("q", "s", TokenBudget(100))
    assert create.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1.0, 2.0]


@pytest.mark.parametrize("stream", [False, True])
async def test_router_preserves_provider_error_metadata(monkeypatch, stream):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("879")])
    monkeypatch.setattr(router, "GroqAdapter", lambda: adapter)
    llm = router.LLMRouter()
    with pytest.raises(LLMRateLimitError) as error:
        if stream:
            async for _ in llm.stream("q", "s", TokenBudget(100)):
                pytest.fail("Rate limited streams must not emit tokens")
        else:
            await llm.generate("q", "s", TokenBudget(100))
    assert error.value.retry_after_seconds == 879
    create.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_short_rate_limit_wait_is_honored_before_retrying(monkeypatch):
    completed = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content="valid completion")
            )
        ]
    )
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("2.25"), completed])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    assert await adapter.generate("q", "s", TokenBudget(100)) == "valid completion"
    sleep.assert_awaited_once_with(3)
    assert create.await_count == 2


async def test_repeated_short_limits_cannot_exceed_wait_budget(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("40")] * 3)
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    with pytest.raises(LLMRateLimitError) as error:
        await adapter.generate("q", "s", TokenBudget(100))
    assert error.value.retry_after_seconds == 40
    assert create.await_count == 2
    sleep.assert_awaited_once_with(40)


async def test_early_cooldown_wakeup_does_not_consume_last_provider_attempt(monkeypatch):
    completed = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content="verified completion")
            )
        ]
    )
    outcomes = [rate_error("9"), rate_error("5"), completed]
    adapter, create, sleep = adapter_with(monkeypatch, [])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    request_times = []

    async def record_request(**kwargs):
        request_times.append(clock[0])
        outcome = outcomes[len(request_times) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    create.side_effect = record_request

    async def advance(delay):
        # Reproduce the observed failure: the second sleep wakes 1 ms early.
        clock[0] += delay - (0.001 if sleep.await_count == 2 else 0)

    sleep.side_effect = advance
    assert await adapter.generate("q", "s", TokenBudget(100)) == "verified completion"
    assert create.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [9, 5, 1]
    assert request_times[1] - request_times[0] >= 9
    assert request_times[2] - request_times[1] >= 5


async def test_existing_cooldown_preserves_all_three_provider_attempts(monkeypatch):
    completed = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))]
    )
    adapter, create, sleep = adapter_with(
        monkeypatch, [rate_error("3"), rate_error("4"), completed]
    )
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    adapter._rate_limit_until = 102.0

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    assert await adapter.generate("q", "s", TokenBudget(100)) == "ok"
    assert create.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [2, 3, 4]


async def test_actual_provider_attempts_remain_capped_at_three(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("2")] * 4)
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    with pytest.raises(LLMRateLimitError):
        await adapter.generate("q", "s", TokenBudget(100))
    assert create.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [2, 2]


async def test_local_cooldown_wait_counts_towards_total_wait_budget(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("25")])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    adapter._rate_limit_until = 140.0

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    with pytest.raises(LLMRateLimitError) as error:
        await adapter.generate("q", "s", TokenBudget(100))
    assert error.value.retry_after_seconds == 25
    create.assert_awaited_once()
    sleep.assert_awaited_once_with(40)


async def test_cooldown_waits_are_bounded_even_if_clock_does_not_advance(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [])
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: 100.0))
    adapter._rate_limit_until = 101.0
    with pytest.raises(LLMRateLimitError):
        await adapter.generate("q", "s", TokenBudget(100))
    create.assert_not_awaited()
    assert sum(call.args[0] for call in sleep.await_args_list) == 60


async def test_rewriter_propagates_provider_failure_instead_of_continuing():
    error = LLMRateLimitError("Groq", 60)
    llm = SimpleNamespace(generate=AsyncMock(side_effect=error))
    with pytest.raises(LLMRateLimitError) as raised:
        await QueryRewriter(llm).rewrite("What did that project use?", ["user: Projects?"])
    assert raised.value is error


@pytest.mark.parametrize("stage", ["plan", "verdict"])
async def test_analyst_does_not_turn_provider_failure_into_missing_evidence(sample_chunks, stage):
    error = LLMRateLimitError("Groq", 60)
    results = [error] if stage == "plan" else ['{"tools":[]}', error]
    llm = SimpleNamespace(generate=AsyncMock(side_effect=results))
    with pytest.raises(LLMRateLimitError) as raised:
        await AnalystAgent(llm).analyze("Question", EvidencePackage(chunks=sample_chunks))
    assert raised.value is error


async def test_provider_failure_is_not_saved_as_a_conversation_answer():
    conversations = SimpleNamespace(save=AsyncMock())
    documents = SimpleNamespace(list_all=AsyncMock(return_value=[]))
    orchestrator = SimpleNamespace(process=AsyncMock(side_effect=LLMRateLimitError("Groq", 60)))
    use_case = AskQuestionUseCase(orchestrator, conversations, documents)
    with pytest.raises(LLMRateLimitError):
        await use_case.execute("Tell me about Nafe's projects")
    conversations.save.assert_not_awaited()
