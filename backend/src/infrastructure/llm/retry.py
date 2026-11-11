import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

import structlog

from src.core.observability import retry_wait
from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMCooldownError,
    LLMRateLimitError,
)

logger = structlog.get_logger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    max_retries: int = 3, base_delay: float = 1.0, max_rate_limit_wait: float = 60.0
) -> Callable[[F], F]:
    """Bound provider attempts and cooldown waiting independently."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            rate_limit_wait = 0.0
            provider_attempts = 0
            while provider_attempts < max_retries:
                try:
                    return await func(*args, **kwargs)
                except LLMConfigurationError:
                    raise
                except LLMRateLimitError as exc:
                    # A cooldown check sends no request. In particular, a sleep that
                    # wakes slightly early must not consume the last provider attempt.
                    local_cooldown = isinstance(exc, LLMCooldownError)
                    if not local_cooldown:
                        provider_attempts += 1
                    delay_hint = exc.retry_after_seconds
                    # A multi-stage answer can hit a short per-minute limit. Honor that
                    # hint within a bounded budget; surface long/unknown waits to the UI.
                    if (
                        provider_attempts >= max_retries
                        or delay_hint is None
                        or delay_hint <= 0
                        or rate_limit_wait + delay_hint > max_rate_limit_wait
                    ):
                        logger.warning(
                            "llm_retry_stopped",
                            provider_attempts=provider_attempts,
                            planned_wait_seconds=delay_hint,
                            wait_budget_seconds=max_rate_limit_wait,
                            wait_used_seconds=rate_limit_wait,
                        )
                        raise
                    rate_limit_wait += delay_hint
                    with retry_wait(
                        delay_hint, "local_cooldown" if local_cooldown else "rate_limit"
                    ):
                        await asyncio.sleep(delay_hint)
                except Exception as e:
                    provider_attempts += 1
                    if provider_attempts >= max_retries:
                        raise
                    delay = base_delay * (2 ** (provider_attempts - 1))
                    logger.warning(
                        "llm_retry_scheduled",
                        attempt=provider_attempts,
                        error_type=type(e).__name__,
                        delay_seconds=delay,
                    )
                    with retry_wait(delay, "transient_error"):
                        await asyncio.sleep(delay)
            return None

        return cast(F, wrapper)

    return decorator
