import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast

from src.domain.exceptions.llm_provider_error import (
    LLMConfigurationError,
    LLMCooldownError,
    LLMRateLimitError,
)

logger = logging.getLogger(__name__)
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
                        raise
                    rate_limit_wait += delay_hint
                    logger.log(
                        logging.INFO if local_cooldown else logging.WARNING,
                        "LLM %s. Honoring Retry-After of %ss.",
                        "local cooldown" if local_cooldown else "rate limited",
                        delay_hint,
                    )
                    await asyncio.sleep(delay_hint)
                except Exception as e:
                    provider_attempts += 1
                    if provider_attempts >= max_retries:
                        raise
                    delay = base_delay * (2 ** (provider_attempts - 1))
                    logger.warning(
                        f"LLM call failed (attempt {provider_attempts}/{max_retries}). "
                        f"Retrying in {delay}s. Error: {e}"
                    )
                    await asyncio.sleep(delay)
            return None

        return cast(F, wrapper)

    return decorator
