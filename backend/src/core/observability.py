"""Request-local diagnostics. Never record prompts, source text, or credentials."""

import functools
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, cast

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProviderRequest:
    call_id: str
    stage: str
    provider: str
    model: str
    max_output_tokens: int
    attempt: int
    status: str = "started"
    status_code: int | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    provider_queue_ms: float | None = None
    provider_generation_ms: float | None = None
    duration_ms: float = 0
    error_type: str | None = None
    rate_limit: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionTrace:
    question_id: str = field(default_factory=lambda: "q_" + uuid.uuid4().hex)
    started: float = field(default_factory=time.perf_counter)
    llm_calls: int = 0
    requests: list[ProviderRequest] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    waits: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        reported = [
            r
            for r in self.requests
            if all(count is not None for count in (r.input_tokens, r.output_tokens, r.total_tokens))
        ]
        return {
            "llm_calls": self.llm_calls,
            "provider_requests": len(self.requests),
            "retries": sum(r.attempt > 1 for r in self.requests),
            "rate_limit_responses": sum(r.status_code == 429 for r in self.requests),
            "input_tokens": sum(r.input_tokens or 0 for r in reported),
            "output_tokens": sum(r.output_tokens or 0 for r in reported),
            "total_tokens": sum(r.total_tokens or 0 for r in reported),
            "cached_input_tokens": sum(r.cached_input_tokens or 0 for r in reported),
            "cached_usage_reported_requests": sum(
                r.cached_input_tokens is not None for r in reported
            ),
            "usage_reported_requests": len(reported),
            "usage_unreported_requests": len(self.requests) - len(reported),
            "usage_complete": len(reported) == len(self.requests),
            "duration_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "provider_duration_ms": round(sum(r.duration_ms for r in self.requests), 2),
            "retry_wait_ms": round(sum(w["duration_ms"] for w in self.waits), 2),
            "waits": list(self.waits),
            "stages": list(self.stages),
            "calls": [asdict(r) for r in self.requests],
        }


_trace: ContextVar[QuestionTrace | None] = ContextVar("question_trace", default=None)
_stage: ContextVar[str] = ContextVar("question_stage", default="unclassified")
_call: ContextVar[str | None] = ContextVar("llm_call", default=None)


def current_trace() -> QuestionTrace | None:
    return _trace.get()


def question_details() -> dict[str, Any]:
    trace = current_trace()
    return {"question_id": trace.question_id, "usage": trace.summary()} if trace else {}


@contextmanager
def question_scope() -> Iterator[QuestionTrace]:
    trace = QuestionTrace()
    token = _trace.set(trace)
    with structlog.contextvars.bound_contextvars(question_id=trace.question_id):
        try:
            yield trace
        finally:
            _trace.reset(token)


@contextmanager
def stage(name: str, **metrics: Any) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    token = _stage.set(name)
    status = "ok"
    with structlog.contextvars.bound_contextvars(stage=name):
        logger.info("stage_started", **metrics)
        try:
            yield metrics
        except BaseException as exc:
            status = "error"
            metrics["error_type"] = type(exc).__name__
            raise
        finally:
            record = {
                **metrics,
                "stage": name,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            trace = current_trace()
            if trace:
                trace.stages.append(record)
            logger.info("stage_completed", **record)
            _stage.reset(token)


@contextmanager
def llm_call_scope() -> Iterator[None]:
    call_id = "llm_" + uuid.uuid4().hex
    token = _call.set(call_id)
    trace = current_trace()
    if trace:
        trace.llm_calls += 1
    with structlog.contextvars.bound_contextvars(call_id=call_id):
        try:
            yield
        finally:
            _call.reset(token)


def llm_operation[F: Callable[..., Any]](func: F) -> F:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        with llm_call_scope():
            return await func(*args, **kwargs)

    return cast(F, wrapper)


@contextmanager
def provider_request(provider: str, model: str, max_output: int) -> Iterator[ProviderRequest]:
    trace = current_trace()
    call_id = _call.get() or "llm_" + uuid.uuid4().hex
    attempt = 1 + sum(r.call_id == call_id for r in trace.requests) if trace else 1
    record = ProviderRequest(call_id, _stage.get(), provider, model, max_output, attempt)
    if trace:
        trace.requests.append(record)
    logger.info("llm_request_started", **asdict(record))
    started = time.perf_counter()
    try:
        yield record
        record.status = "ok"
    except BaseException as exc:
        record.status = "error"
        record.error_type = type(exc).__name__
        raise
    finally:
        record.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info("llm_request_completed", **asdict(record))


@contextmanager
def retry_wait(seconds: float, reason: str) -> Iterator[None]:
    started = time.perf_counter()
    metrics = {"stage": _stage.get(), "reason": reason, "planned_seconds": seconds}
    logger.info("llm_retry_wait_started", **metrics)
    try:
        yield
    finally:
        metrics["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        trace = current_trace()
        if trace:
            trace.waits.append(metrics)
        logger.info("llm_retry_wait_completed", **metrics)
