import asyncio
import json

import pytest

from src.api.chat_stream import stream_question
from src.core.observability import stage
from src.core.progress import current_progress, progress_scope
from src.domain.exceptions.llm_provider_error import LLMRateLimitError


def result():
    return {
        "answer": "Verified answer",
        "state": "answer_ready",
        "loops": 0,
        "evidence_count": 1,
        "sources": [],
        "tool_results": [],
        "conversation_id": "conv_test",
    }


def event(frame):
    return json.loads(frame.removeprefix("data: "))


async def test_progress_arrives_before_work_finishes_and_collects_all_tool_calls():
    release = asyncio.Event()

    async def execute():
        for _ in range(2):
            with (
                stage("retrieval", private_question="SECRET"),
                stage("vector_search", private_source="SECRET"),
            ):
                await release.wait()
            with stage("analysis"), stage("analyst_tool", tool_name="calculator"):
                pass
        with stage("answer_verification"):
            pass
        return result()

    stream = stream_question(execute)
    assert await anext(stream) == ": connected\n\n"
    first = event(await asyncio.wait_for(anext(stream), 1))
    assert first["step"]["status"] == "running"
    assert first["step"]["agent"] == "retriever"
    assert not release.is_set()
    release.set()
    frames = [frame async for frame in stream]
    assert "SECRET" not in "".join(frames)
    answer = event(frames[-1])["result"]
    assert [tool["name"] for tool in answer["tools_used"]] == ["hybrid_search", "calculator"]
    assert all(tool["calls"] == tool["completed"] == 2 for tool in answer["tools_used"])
    assert all(step["status"] == "completed" for step in answer["activity"])
    assert current_progress() is None


async def test_closing_stream_cancels_pending_work():
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def execute():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return result()

    stream = stream_question(execute)
    await anext(stream)
    await asyncio.wait_for(entered.wait(), 1)
    await stream.aclose()
    assert cancelled.is_set()
    assert current_progress() is None


@pytest.mark.parametrize("error", [RuntimeError("SECRET"), LLMRateLimitError("Groq", 45)])
async def test_stream_error_never_emits_a_result_or_raw_runtime_error(error):
    async def execute():
        with stage("analysis"):
            raise error

    frames = [frame async for frame in stream_question(execute)]
    payloads = [event(frame) for frame in frames if frame.startswith("data:")]
    assert payloads[-2]["step"]["status"] == "failed"
    assert payloads[-1]["type"] == "error"
    assert not any(payload["type"] == "result" for payload in payloads)
    assert "SECRET" not in "".join(frames)
    if isinstance(error, LLMRateLimitError):
        assert payloads[-1]["error"]["status"] == 429
        assert payloads[-1]["error"]["details"]["retry_after_seconds"] == 45


async def test_progress_isolated_between_concurrent_questions_and_counts_failures():
    async def run(tool):
        with progress_scope() as trace:
            with stage("analysis"):
                await asyncio.sleep(0)
                with pytest.raises(ValueError), stage("analyst_tool", tool_name=tool):
                    raise ValueError("private tool input")
            return trace.tools()

    first, second = await asyncio.gather(run("calculator"), run("data_analysis"))
    assert first[0]["name"] == "calculator"
    assert second[0]["name"] == "data_analysis"
    assert first[0]["failed"] == second[0]["failed"] == 1
    assert first[0]["completed"] == 0


def test_unlisted_stages_and_tool_names_are_not_exposed():
    with (
        progress_scope() as trace,
        stage("private_internal_stage", text="SECRET"),
        stage("analyst_tool", tool_name="SECRET"),
    ):
        pass
    assert trace.steps == []
