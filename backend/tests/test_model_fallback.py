from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from groq import AuthenticationError

from src.core.observability import question_scope, stage
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import groq_adapter, retry, router
from tests.test_llm_provider_errors import rate_error
from tests.test_observability import completion

MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-safeguard-20b",
]


def setup_router(monkeypatch, outcomes):
    create = AsyncMock(side_effect=outcomes)
    monkeypatch.setattr(
        groq_adapter,
        "AsyncGroq",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    monkeypatch.setattr(router.settings, "LLM_MODEL", MODELS[0])
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MODELS", MODELS[1:])
    sleep = AsyncMock()
    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    return router.LLMRouter(), create, sleep


@pytest.mark.parametrize("successful_index", range(4))
async def test_fallback_order_is_immediate_and_usage_stays_under_one_call(
    monkeypatch, successful_index
):
    llm, create, sleep = setup_router(
        monkeypatch, [rate_error("60")] * successful_index + [completion()]
    )
    with question_scope() as trace, stage("answer_verification"):
        assert await llm.generate("private prompt", "private source", TokenBudget(100)) == "ok"
    assert [c.kwargs["model"] for c in create.await_args_list] == MODELS[: successful_index + 1]
    assert all(c.kwargs["max_tokens"] == 100 for c in create.await_args_list)
    sleep.assert_not_awaited()
    summary = trace.summary()
    assert summary["llm_calls"] == 1
    assert summary["provider_requests"] == successful_index + 1
    assert summary["rate_limit_responses"] == successful_index
    assert summary["total_tokens"] == 125
    assert summary["usage_unreported_requests"] == successful_index
    assert len({r.call_id for r in trace.requests}) == 1
    assert all(r.stage == "answer_verification" for r in trace.requests)


async def test_cooldown_is_per_model_and_primary_is_retried_after_expiry(monkeypatch):
    llm, create, sleep = setup_router(
        monkeypatch,
        [rate_error("20"), rate_error("5"), completion(), completion(), completion(), completion()],
    )
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    with question_scope() as trace:
        await llm.generate("q", "s", TokenBudget(100))
        # Primary and secondary are cooling down; do not send another HTTP request to them.
        await llm.generate("q", "s", TokenBudget(100))
        clock[0] += 6
        await llm.generate("q", "s", TokenBudget(100))
        clock[0] += 15
        await llm.generate("q", "s", TokenBudget(100))
    assert [c.kwargs["model"] for c in create.await_args_list] == [
        MODELS[0],
        MODELS[1],
        MODELS[2],
        MODELS[2],
        MODELS[1],
        MODELS[0],
    ]
    assert trace.summary()["llm_calls"] == 4
    assert trace.summary()["provider_requests"] == 6
    sleep.assert_not_awaited()


async def test_all_models_limited_return_earliest_known_reset_without_retry_storm(monkeypatch):
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MAX_WAIT_SECONDS", 0)
    llm, create, sleep = setup_router(
        monkeypatch, [rate_error("90"), rate_error("20"), rate_error(None), rate_error("40")]
    )
    for _ in range(2):
        with pytest.raises(LLMRateLimitError) as error:
            await llm.generate("q", "s", TokenBudget(100))
        assert error.value.retry_after_seconds == 20
        if create.await_count == 4:
            # Unknown reset times cannot be cached or invented. On the next call,
            # only this model is requested again.
            create.side_effect = [rate_error(None)]
    assert create.await_count == 5
    sleep.assert_not_awaited()


async def test_all_models_limited_resume_same_call_after_earliest_reset(monkeypatch):
    from src.core.progress import progress_scope

    llm, create, sleep = setup_router(
        monkeypatch,
        [rate_error("90"), rate_error("5"), rate_error("30"), rate_error("40"), completion()],
    )
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    sleep.side_effect = lambda delay: clock.__setitem__(0, clock[0] + delay)
    with question_scope() as trace, progress_scope() as progress, stage("answer_verification"):
        assert await llm.generate("draft", "review", TokenBudget(100)) == "ok"
    sleep.assert_awaited_once_with(5)
    assert create.await_args.kwargs["model"] == MODELS[1]
    assert trace.summary()["llm_calls"] == 1
    assert trace.waits[0]["planned_seconds"] == 5
    waiting = next(s for s in progress.steps if s["label"] == "Waiting for provider capacity")
    assert waiting["agent"] == "verification" and waiting["status"] == "completed"


async def test_fallback_wait_budget_is_shared_across_question_stages(monkeypatch):
    llm, create, sleep = setup_router(
        monkeypatch, [rate_error("40")] * 4 + [completion()] + [rate_error("30")] * 4
    )
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    sleep.side_effect = lambda delay: clock.__setitem__(0, clock[0] + delay)
    with question_scope():
        assert await llm.generate("q", "s", TokenBudget(100)) == "ok"
        with pytest.raises(LLMRateLimitError):
            await llm.generate("review", "s", TokenBudget(100))
    sleep.assert_awaited_once_with(40)
    assert create.await_count == 9


async def test_fresh_reset_hint_takes_priority_over_cached_smaller_prompt_limit(monkeypatch):
    llm, create, sleep = setup_router(monkeypatch, [rate_error("15"), rate_error("30"),
                                                 rate_error("40"), completion()])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    llm.providers[0]._rate_limit_until = 102.0
    sleep.side_effect = lambda delay: clock.__setitem__(0, clock[0] + delay)
    assert await llm.generate("larger prompt", "s", TokenBudget(100)) == "ok"
    sleep.assert_awaited_once_with(15)
    assert create.await_count == 4


async def test_repeated_limits_stop_after_one_wait_and_cancellation_propagates(monkeypatch):
    import asyncio

    llm, create, sleep = setup_router(monkeypatch, [rate_error("2")] * 8)
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    sleep.side_effect = lambda delay: clock.__setitem__(0, clock[0] + delay)
    with pytest.raises(LLMRateLimitError):
        await llm.generate("q", "s", TokenBudget(100))
    sleep.assert_awaited_once_with(2)
    assert create.await_count == 8
    sleep.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await llm.generate("q", "s", TokenBudget(100))
    assert create.await_count == 8


async def test_unknown_resets_remain_unknown(monkeypatch):
    llm, create, sleep = setup_router(monkeypatch, [rate_error(None)] * 4)
    with pytest.raises(LLMRateLimitError) as error:
        await llm.generate("q", "s", TokenBudget(100))
    assert error.value.retry_after_seconds is None
    assert create.await_count == 4
    sleep.assert_not_awaited()


async def test_authentication_failure_does_not_try_other_models(monkeypatch):
    response = httpx.Response(401, request=httpx.Request("POST", "https://provider.test"))
    llm, create, sleep = setup_router(
        monkeypatch, [AuthenticationError("private credentials", response=response, body=None)]
    )
    with pytest.raises(LLMConfigurationError):
        await llm.generate("q", "s", TokenBudget(100))
    create.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_repeated_truncation_stops_after_one_alternative(monkeypatch):
    llm, create, _ = setup_router(monkeypatch, [completion(finish="length")] * 3)
    with pytest.raises(LLMOutputError, match="incomplete") as error:
        await llm.generate("q", "s", TokenBudget(100))
    assert error.value.finish_reason == "length"
    assert [c.kwargs["model"] for c in create.await_args_list] == MODELS[:2]


async def test_truncation_uses_complete_alternative_without_increasing_budget(monkeypatch):
    llm, create, sleep = setup_router(
        monkeypatch, [completion(finish="length"), completion()]
    )
    with question_scope() as trace:
        assert await llm.generate("q", "s", TokenBudget(100)) == "ok"
    assert [c.kwargs["model"] for c in create.await_args_list] == MODELS[:2]
    assert all(c.kwargs["max_tokens"] == 100 for c in create.await_args_list)
    assert trace.summary()["llm_calls"] == 1
    assert trace.summary()["provider_requests"] == 2
    assert trace.requests[0].finish_reason == "length"
    sleep.assert_not_awaited()


@pytest.mark.parametrize("finish", ["stop", "content_filter", "error", None])
async def test_other_invalid_outputs_do_not_switch_models(monkeypatch, finish):
    response = completion(finish=finish)
    response.choices[0].message.content = ""
    llm, create, sleep = setup_router(monkeypatch, [response])
    with pytest.raises(LLMOutputError):
        await llm.generate("q", "s", TokenBudget(100))
    create.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_single_truncated_provider_is_not_blindly_replayed(monkeypatch):
    llm, create, sleep = setup_router(monkeypatch, [completion(finish="length")])
    llm.providers = llm.providers[:1]
    with pytest.raises(LLMOutputError):
        await llm.generate("q", "s", TokenBudget(100))
    create.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.parametrize("elapsed,expected_wait", [(37, None), (3, 5)])
@pytest.mark.parametrize("failure_kind", ["length", "timeout"])
async def test_slow_truncated_fallback_can_recover_earlier_limited_model(
    monkeypatch, elapsed, expected_wait, failure_kind
):
    llm, create, sleep = setup_router(monkeypatch, [rate_error("8"), completion()])
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MAX_WAIT_SECONDS", 60)
    clock = [100.0]
    timer = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(groq_adapter, "time", timer)
    monkeypatch.setattr(router, "time", timer)
    sleep.side_effect = lambda delay: clock.__setitem__(0, clock[0] + delay)

    async def truncated(*args):
        clock[0] += elapsed
        if failure_kind == "timeout":
            raise LLMTimeoutError("OpenRouter")
        raise LLMOutputError("OpenRouter", finish_reason="length")

    fallback = SimpleNamespace(model="openrouter/free", generate_for_router=AsyncMock(side_effect=truncated))
    llm.providers = llm.providers[:1] + [fallback]
    with question_scope() as trace:
        assert await llm.generate("q", "s", TokenBudget(3000, json_output=True)) == "ok"
    assert create.await_count == 2
    assert all(c.kwargs["model"] == MODELS[0] for c in create.await_args_list)
    fallback.generate_for_router.assert_awaited_once()
    assert trace.summary()["llm_calls"] == 1
    if expected_wait is None:
        sleep.assert_not_awaited()
    else:
        sleep.assert_awaited_once_with(expected_wait)


@pytest.mark.parametrize("reset,wait_budget", [("8", 0), (None, 60)])
async def test_truncated_recovery_respects_unknown_resets_and_wait_budget(
    monkeypatch, reset, wait_budget
):
    llm, create, sleep = setup_router(monkeypatch, [rate_error(reset)])
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MAX_WAIT_SECONDS", wait_budget)
    fallback = SimpleNamespace(
        model="openrouter/free",
        generate_for_router=AsyncMock(
            side_effect=LLMOutputError("OpenRouter", finish_reason="length")
        ),
    )
    llm.providers = llm.providers[:1] + [fallback]
    with pytest.raises(LLMOutputError):
        await llm.generate("q", "s", TokenBudget(3000, json_output=True))
    create.assert_awaited_once()
    fallback.generate_for_router.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_repeated_provider_timeouts_stop_after_one_alternative(monkeypatch):
    llm, _, sleep = setup_router(monkeypatch, [])
    providers = [
        SimpleNamespace(
            model=f"test-{index}",
            generate_for_router=AsyncMock(side_effect=LLMTimeoutError("test")),
        )
        for index in range(3)
    ]
    llm.providers = providers
    with pytest.raises(LLMTimeoutError):
        await llm.generate("q", "s", TokenBudget(100))
    assert [p.generate_for_router.await_count for p in providers] == [1, 1, 0]
    sleep.assert_not_awaited()


async def test_config_deduplicates_models_and_can_disable_fallback(monkeypatch):
    llm, _, _ = setup_router(monkeypatch, [])
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MODELS", [MODELS[0], " ", MODELS[1]] * 2)
    llm = router.LLMRouter()
    assert [p.model for p in llm.providers] == MODELS[:2]
    monkeypatch.setattr(router.settings, "LLM_FALLBACK_MODELS", [])
    assert [p.model for p in router.LLMRouter().providers] == MODELS[:1]


async def test_stream_falls_back_only_before_emitting_output(monkeypatch):
    async def tokens():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))])

    llm, create, sleep = setup_router(monkeypatch, [rate_error("90"), tokens()])
    with question_scope() as trace:
        assert [t async for t in llm.stream("q", "s", TokenBudget(100))] == ["hello"]
    assert [c.kwargs["model"] for c in create.await_args_list] == MODELS[:2]
    assert trace.summary()["llm_calls"] == 1
    assert len({r.call_id for r in trace.requests}) == 1
    sleep.assert_not_awaited()


async def test_partial_stream_is_not_replayed_on_another_model(monkeypatch):
    async def tokens():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="first"))])
        raise rate_error("20")

    llm, create, sleep = setup_router(monkeypatch, [tokens()])
    received = []
    with pytest.raises(LLMRateLimitError):
        async for token in llm.stream("q", "s", TokenBudget(100)):
            received.append(token)
    assert received == ["first"]
    create.assert_awaited_once()
    sleep.assert_not_awaited()
