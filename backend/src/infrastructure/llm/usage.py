"""Extract only allowlisted provider diagnostics, never raw error bodies."""

import re
from typing import Any

from groq import APIError, APIStatusError

from src.core.observability import ProviderRequest


def value(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def record_response(record: ProviderRequest, response: Any) -> None:
    record.status_code = 200
    metadata = value(response, "x_groq")
    request_id = value(metadata, "id")
    if isinstance(request_id, str):
        record.provider_request_id = request_id
    usage = value(response, "usage") or value(metadata, "usage")
    if usage is None:
        return
    # Do not invent zero usage when the provider omits its accounting fields.
    for target, source in (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        count = value(usage, source)
        if isinstance(count, int) and count >= 0:
            setattr(record, target, count)
    for target, details, source in (
        ("cached_input_tokens", "prompt_tokens_details", "cached_tokens"),
        ("reasoning_tokens", "completion_tokens_details", "reasoning_tokens"),
    ):
        count = value(value(usage, details), source)
        if isinstance(count, int) and count >= 0:
            setattr(record, target, count)
    for target, source in (
        ("provider_queue_ms", "queue_time"),
        ("provider_generation_ms", "completion_time"),
    ):
        seconds = value(usage, source)
        if isinstance(seconds, (int, float)) and seconds >= 0:
            setattr(record, target, round(seconds * 1000, 2))


def record_error(record: ProviderRequest, error: APIError) -> None:
    if not isinstance(error, APIStatusError):
        return
    record.status_code = error.status_code
    record.provider_request_id = error.response.headers.get("x-request-id")
    for header in (
        "retry-after",
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
    ):
        if header in error.response.headers:
            record.rate_limit[header] = error.response.headers[header][:80]
    if error.status_code == 429:
        # The error text also contains private organization IDs. Extract only quota numbers.
        match = re.search(
            r"on (tokens|requests) per (minute|day) \(([A-Z]+)\): Limit ([\d.]+), Used ([\d.]+), Requested ([\d.]+)",
            str(error),
        )
        if match:
            record.rate_limit.update(
                limit_type=match[3],
                limit=float(match[4]),
                used=float(match[5]),
                requested=float(match[6]),
            )
