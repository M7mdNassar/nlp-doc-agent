"""Deterministic checks for explicit answer length requests."""

import re

from src.domain.entities.answer import AnswerDraft


class AnswerLengthError(ValueError):
    """The generated text violates an explicit answer-length requirement."""


def word_requirement(question: str) -> tuple[int, bool] | None:
    match = re.search(
        r"\b(in|exactly|at most|no more than|under|fewer than|up to)\s+(\d+)\s+words\b",
        question,
        re.I,
    )
    if match is None:
        return None
    mode, number = match.groups()
    limit = int(number)
    if mode.casefold() in {"under", "fewer than"}:
        limit -= 1
    return limit, mode.casefold() in {"in", "exactly"}


def length_instruction(question: str) -> str:
    requirement = word_requirement(question)
    if requirement is None:
        return ""
    limit, exact = requirement
    qualifier = "exactly" if exact else "at most"
    return (
        f"Use {qualifier} {limit} whitespace-separated words across all block text. "
        "Hyphenated words count as one. Citation metadata is excluded."
    )


def validate_length(question: str, draft: AnswerDraft) -> None:
    requirement = word_requirement(question)
    if requirement is None:
        return
    limit, exact = requirement
    count = sum(len(block.text.split()) for block in draft.blocks)
    if (exact and count != limit) or count > limit:
        raise AnswerLengthError(f"Answer has {count} words. {length_instruction(question)}")
