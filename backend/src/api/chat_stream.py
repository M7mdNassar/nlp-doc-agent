import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

import structlog

from src.core.errors import AppError
from src.core.observability import current_trace
from src.core.progress import ProgressTrace, progress_scope
from src.domain.entities.answer import ChatResult
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
)

logger = structlog.get_logger(__name__)


def complete_result(result: ChatResult, progress: ProgressTrace) -> ChatResult:
    result["activity"] = progress.steps
    result["tools_used"] = progress.tools()
    trace = current_trace()
    if trace:
        result["question_id"] = trace.question_id
        result["usage"] = trace.summary()
    return result


def stream_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {"status": exc.status_code, "code": exc.code, "message": exc.message}
    if isinstance(exc, LLMRateLimitError):
        return {
            "status": 429,
            "code": "LLM_RATE_LIMITED",
            "message": "The AI provider has reached a usage limit.",
            "details": {"retry_after_seconds": exc.retry_after_seconds},
        }
    if isinstance(exc, LLMConfigurationError):
        return {
            "status": 503,
            "code": "LLM_CONFIGURATION_ERROR",
            "message": "The AI provider could not accept the request. Check the backend configuration.",
        }
    if isinstance(exc, LLMProviderError):
        return {
            "status": 503,
            "code": "LLM_UNAVAILABLE",
            "message": "The AI provider is temporarily unavailable. Please try again.",
        }
    return {
        "status": 500,
        "code": "INTERNAL_ERROR",
        "message": "The question could not be processed. Please try again.",
    }


async def stream_question(execute: Callable[[], Awaitable[ChatResult]]) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def run() -> None:
        with progress_scope(
            lambda step: queue.put_nowait({"type": "progress", "step": step})
        ) as progress:
            try:
                result = complete_result(await execute(), progress)
                queue.put_nowait({"type": "result", "result": result})
            except Exception as exc:
                logger.warning("chat_stream_failed", error_type=type(exc).__name__)
                queue.put_nowait({"type": "error", "error": stream_error(exc)})
            finally:
                queue.put_nowait(None)

    task = asyncio.create_task(run())
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                break
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
