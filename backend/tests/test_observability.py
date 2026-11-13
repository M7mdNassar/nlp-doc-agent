import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.observability import current_trace, question_scope, stage
from src.domain.exceptions.llm_provider_error import LLMRateLimitError
from src.domain.value_objects.token_budget import TokenBudget
from src.infrastructure.llm import groq_adapter
from tests.test_llm_provider_errors import adapter_with, rate_error


def completion(input_tokens=100, output_tokens=25, finish="stop", content="ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=30),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
            queue_time=0.01,
            completion_time=0.2,
        ),
        x_groq=SimpleNamespace(id="req_provider"),
    )


async def test_usage_includes_truncated_completions_and_actual_retry_requests(monkeypatch):
    adapter, create, _ = adapter_with(monkeypatch, [completion(finish="length"), completion()])
    with question_scope() as trace, stage("answer_generation"):
        assert (
            await adapter.generate("private question", "private document", TokenBudget(100)) == "ok"
        )
        summary = trace.summary()
    assert create.await_count == 2
    assert summary["llm_calls"] == 1
    assert summary["provider_requests"] == 2 and summary["retries"] == 1
    assert summary["input_tokens"] == 200 and summary["output_tokens"] == 50
    assert summary["total_tokens"] == 250 and summary["cached_input_tokens"] == 60
    assert summary["usage_complete"]
    assert summary["calls"][0]["finish_reason"] == "length"
    assert summary["calls"][0]["status"] == "error"
    assert summary["calls"][1]["status"] == "ok"
    assert summary["calls"][0]["stage"] == "answer_generation"
    assert summary["calls"][0]["provider_request_id"] == "req_provider"
    assert summary["calls"][0]["reasoning_tokens"] == 5
    assert "private" not in json.dumps(summary)
    assert current_trace() is None


async def test_rate_limits_do_not_invent_tokens_and_cooldowns_are_not_provider_calls(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("2"), completion()])
    clock = [100.0]
    monkeypatch.setattr(groq_adapter, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    adapter._rate_limit_until = 103.0

    async def advance(delay):
        clock[0] += delay

    sleep.side_effect = advance
    with question_scope() as trace, stage("tool_plan"):
        await adapter.generate("q", "s", TokenBudget(100))
    summary = trace.summary()
    assert create.await_count == 2
    assert summary["provider_requests"] == 2
    assert summary["rate_limit_responses"] == 1
    assert summary["total_tokens"] == 125
    assert summary["usage_reported_requests"] == 1
    assert summary["usage_unreported_requests"] == 1
    assert not summary["usage_complete"]
    assert summary["calls"][0]["total_tokens"] is None
    assert [w["reason"] for w in trace.waits] == ["local_cooldown", "rate_limit"]
    assert [w["planned_seconds"] for w in trace.waits] == [3, 2]


async def test_failure_keeps_prior_usage_and_separates_parallel_questions(monkeypatch):
    barrier = asyncio.Barrier(2)

    async def create(**kwargs):
        prompt = kwargs["messages"][1]["content"]
        await barrier.wait()
        return completion(100 if prompt == "first" else 200)

    monkeypatch.setattr(
        groq_adapter,
        "AsyncGroq",
        Mock(
            return_value=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )
        ),
    )
    adapter = groq_adapter.GroqAdapter()

    async def question(name):
        with question_scope() as trace:
            with stage("analysis_verdict"):
                await adapter.generate(name, "secret", TokenBudget(100))
            try:
                with stage("answer_generation"):
                    raise ValueError("private model output")
            except ValueError:
                pass
            return trace.question_id, trace.summary()

    first, second = await asyncio.gather(question("first"), question("second"))
    assert first[0] != second[0]
    assert first[1]["input_tokens"] == 100
    assert second[1]["input_tokens"] == 200
    assert first[1]["provider_requests"] == second[1]["provider_requests"] == 1
    assert first[1]["stages"][-1]["status"] == "error"
    assert "private" not in json.dumps(first)
    assert current_trace() is None


async def test_missing_usage_is_explicitly_unknown(monkeypatch):
    response = completion()
    response.usage = None
    adapter, _, _ = adapter_with(monkeypatch, [response])
    with question_scope() as trace:
        await adapter.generate("q", "s", TokenBudget(100))
    assert trace.summary()["usage_unreported_requests"] == 1
    assert trace.summary()["calls"][0]["input_tokens"] is None


async def test_stream_final_usage_without_choices_is_recorded_once(monkeypatch):
    response = completion()

    class Stream:
        closed = False

        async def __aiter__(self):
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"), finish_reason=None)],
                usage=None,
                x_groq=None,
            )
            yield SimpleNamespace(
                choices=[],
                usage=None,
                x_groq=SimpleNamespace(id="req_stream", usage=response.usage),
            )

        async def close(self):
            self.closed = True

    stream = Stream()
    adapter, _, _ = adapter_with(monkeypatch, [stream])
    with question_scope() as trace, stage("answer_generation"):
        assert [item async for item in adapter.stream("q", "s", TokenBudget(100))] == ["ok"]
    assert trace.summary()["total_tokens"] == 125
    assert trace.summary()["provider_requests"] == 1
    assert stream.closed


async def test_failed_question_usage_survives_provider_error(monkeypatch):
    adapter, _, _ = adapter_with(monkeypatch, [completion(), rate_error("900")])
    with question_scope() as trace:
        await adapter.generate("q", "s", TokenBudget(100))
        with pytest.raises(LLMRateLimitError):
            await adapter.generate("q", "s", TokenBudget(100))
    summary = trace.summary()
    assert summary["llm_calls"] == 2
    assert summary["total_tokens"] == 125
    assert summary["rate_limit_responses"] == 1
    assert summary["retries"] == 0


async def test_cancelled_wait_is_recorded_without_another_provider_request(monkeypatch):
    adapter, create, sleep = adapter_with(monkeypatch, [rate_error("2")])
    sleep.side_effect = asyncio.CancelledError()
    with question_scope() as trace, pytest.raises(asyncio.CancelledError):
        await adapter.generate("q", "s", TokenBudget(100))
    assert create.await_count == 1
    assert len(trace.waits) == 1
    assert current_trace() is None
