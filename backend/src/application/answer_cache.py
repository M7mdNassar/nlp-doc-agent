"""Reuse only verified answers in the same corpus, pipeline and request scope."""

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Literal

import structlog
from pydantic import Field

from src.core.errors import AppError
from src.core.observability import stage
from src.domain.entities.analysis import StrictModel
from src.domain.entities.answer import ChatResult, Source
from src.domain.ports.answer_cache import AnswerCacheStore, CacheCorpus
from src.domain.ports.embedder import Embedder

logger = structlog.get_logger(__name__)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def normalize(question: str) -> str:
    # Preserve case, symbols, numbers, negation and all output requirements.
    return question.strip()


def semantic_guard(question: str) -> str | None:
    """A deliberately narrow set of equivalent definition requests.

    Subject, order, case, quantities and output instructions must remain identical.
    Similarity alone never authorizes reuse of a differently scoped question.
    """
    if any(char in question for char in ("`", "'", '"', "\n")):
        return None
    match = re.fullmatch(
        r"(?:What is|What are|Explain|Describe|Define|Tell me about)\s+(.+?)[?.]?",
        normalize(question),
        re.I,
    )
    return digest(match[1]) if match else None


class CachedAnswer(StrictModel):
    scope: str
    guard: str | None
    verified: Literal[True]
    created: float
    expires: float
    answer: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    evidence_count: int
    tool_results: list[dict[str, Any]]

    def result(self, kind: str, score: float | None) -> ChatResult:
        return ChatResult(
            answer=self.answer,
            state="answer_ready",
            loops=0,
            sources=self.sources,
            evidence_count=self.evidence_count,
            tool_results=self.tool_results,
            conversation_id="",
            cache={
                "status": kind,
                "age_seconds": round(max(0, time.time() - self.created), 2),
                "similarity": score,
            },
        )


class AnswerCache:
    def __init__(
        self,
        store: AnswerCacheStore,
        corpus: CacheCorpus,
        embedder: Embedder,
        parameters: str,
        ttl: int = 86400,
        semantic: bool = True,
        threshold: float = 0.94,
        wait_seconds: float = 300,
    ):
        self.store, self.corpus, self.embedder = store, corpus, embedder
        self.parameters, self.ttl, self.semantic = parameters, ttl, semantic
        self.threshold, self.wait_seconds = threshold, wait_seconds

    async def _safe[T](self, operation: Callable[[], Awaitable[T]]) -> T | None:
        try:
            return await operation()
        except Exception as exc:
            logger.warning("answer_cache_unavailable", error_type=type(exc).__name__)
            return None

    async def _entry(self, key: str, scope: str) -> CachedAnswer | None:
        data = await self._safe(lambda: self.store.get(key))
        if data is None:
            return None
        try:
            entry = CachedAnswer.model_validate(data)
            if entry.scope != scope or entry.expires <= time.time():
                return None
            with stage("cached_source_validation"):
                if not await self.corpus.supports(entry.sources):
                    return None
            return entry
        except Exception as exc:
            logger.warning("answer_cache_entry_rejected", error_type=type(exc).__name__)
            return None

    async def _lookup(
        self, key: str, scope: str, guard: str | None, vector: list[float] | None
    ) -> ChatResult | None:
        with stage("cache_lookup") as metrics:
            entry = await self._entry(key, scope)
            if entry:
                metrics["cache_status"] = "exact_hit"
                return entry.result("exact_hit", None)
            if guard and vector:
                matches = await self._safe(
                    lambda: self.store.find(vector, scope, guard, self.threshold)
                )
                for candidate, score in matches or []:
                    entry = await self._entry(candidate, scope)
                    if entry and entry.guard == guard:
                        metrics["cache_status"] = "semantic_hit"
                        return entry.result("semantic_hit", score)
            metrics["cache_status"] = "miss"
            return None

    async def run(
        self,
        question: str,
        filters: dict[str, Any],
        history: list[str],
        generate: Callable[[], Awaitable[ChatResult]],
    ) -> ChatResult:
        revision = await self._safe(self.corpus.revision)
        if revision is None:
            return await self._bypass(generate, "unavailable")
        canonical_filters = {k: sorted(v) if isinstance(v, list) else v for k, v in filters.items()}
        scope = digest([revision, self.parameters, canonical_filters, history])
        key = digest([scope, normalize(question)])
        # Contextual requests use exact matching with their full effective history.
        guard = semantic_guard(question) if self.semantic and not history else None
        hit = await self._lookup(key, scope, None, None)
        vector = None
        if hit is None and guard:
            vector = await self._safe(lambda: self.embedder.embed_query(normalize(question)))
            hit = await self._lookup(key, scope, guard, vector)
        if hit and await self._safe(self.corpus.revision) == revision:
            return self._reuse(hit)
        try:
            hit, token = await self._acquire(key, scope, revision)
        except AppError:
            raise
        except Exception:
            return await self._bypass(generate, "unavailable")
        if hit:
            return self._reuse(hit)
        assert token is not None
        renewal = asyncio.create_task(self._renew(key, token))
        try:
            # A winner may have populated the entry between our lookup and claim.
            hit = await self._lookup(key, scope, None, None)
            if hit and await self._safe(self.corpus.revision) == revision:
                return self._reuse(hit)
            result = await generate()
            result["cache"] = {"status": "miss"}
            if (
                result["state"] == "answer_ready"
                and result["sources"]
                and await self._safe(self.corpus.revision) == revision
            ):
                await self._safe(lambda: self._store(key, scope, guard, vector, result))
            return result
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            await self._safe(lambda: self.store.release(key, token))

    async def _acquire(
        self, key: str, scope: str, revision: str
    ) -> tuple[ChatResult | None, str | None]:
        token = await self.store.claim(key)
        if token:
            return None, token
        hit, token = await self._wait(key, scope, revision)
        if hit is None and token is None:
            raise AppError(
                "ANSWER_IN_PROGRESS",
                "An identical question is still processing. Please retry shortly.",
                503,
            )
        return hit, token

    async def _wait(
        self, key: str, scope: str, revision: str
    ) -> tuple[ChatResult | None, str | None]:
        deadline = time.monotonic() + self.wait_seconds
        with stage("cache_wait"):
            while time.monotonic() < deadline:
                entry = await self._entry(key, scope)
                if entry and await self._safe(self.corpus.revision) == revision:
                    return entry.result("exact_hit", None), None
                token = await self.store.claim(key)
                if token:
                    return None, token
                await asyncio.sleep(0.5)
        return None, None

    async def _renew(self, key: str, token: str) -> None:
        while True:
            await asyncio.sleep(30)
            await self._safe(lambda: self.store.renew(key, token))

    async def _store(
        self,
        key: str,
        scope: str,
        guard: str | None,
        vector: list[float] | None,
        result: ChatResult,
    ) -> None:
        now = time.time()
        entry = CachedAnswer(
            scope=scope,
            guard=guard,
            verified=True,
            created=now,
            expires=now + self.ttl,
            answer=result["answer"],
            sources=result["sources"],
            evidence_count=result["evidence_count"],
            tool_results=result["tool_results"],
        )
        await self._safe(lambda: self.store.set(key, entry.model_dump(), self.ttl))
        if vector and guard:
            await self._safe(lambda: self.store.index(key, vector, scope, guard, entry.expires))

    @staticmethod
    def _reuse(result: ChatResult) -> ChatResult:
        with stage("cache_reuse", cache_status=result["cache"]["status"]):
            return result

    @staticmethod
    async def _bypass(generate: Callable[[], Awaitable[ChatResult]], reason: str) -> ChatResult:
        result = await generate()
        result["cache"] = {"status": "bypass", "reason": reason}
        return result
