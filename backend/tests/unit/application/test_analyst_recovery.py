import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from structlog.testing import capture_logs

from src.application.agents.analyst.analyst_agent import AnalystAgent
from src.application.tools.analyst_tools import AnalystTools
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.core.errors import AnalysisOutputError
from src.core.observability import question_scope
from src.domain.entities.evidence import EvidencePackage
from src.domain.exceptions.llm_provider_error import LLMRateLimitError
from tests.test_llm_provider_errors import adapter_with
from tests.test_observability import completion
from tests.unit.application.test_orchestrator import make_orchestrator


def verdict(**updates):
    return json.dumps(
        {
            "has_enough_evidence": True,
            "missing_info": "",
            "findings": [{"text": "Model X is 95% accurate.", "chunk_ids": ["chunk_1"]}],
            **updates,
        }
    )


@pytest.mark.parametrize(
    "bad,category,check",
    [
        ("PRIVATE_INVALID_JSON", "json", None),
        (verdict(has_enough_evidence="true"), "schema", None),
        (verdict(findings=[]), "grounding", "missing_grounded_findings"),
        (
            verdict(findings=[{"text": "PRIVATE_CLAIM", "chunk_ids": ["PRIVATE_ID"]}]),
            "grounding",
            "unknown_chunk_reference",
        ),
        (verdict(PRIVATE_KEY="PRIVATE_VALUE"), "schema", None),
    ],
)
async def test_bad_verdict_corrected_on_same_evidence_without_replanning(
    sample_chunks,
    bad,
    category,
    check,
):
    llm = SimpleNamespace(generate=AsyncMock(side_effect=['{"tools":[]}', bad, verdict()]))
    with capture_logs() as logs, question_scope() as trace:
        result = await AnalystAgent(llm).analyze(
            "PRIVATE_QUESTION", EvidencePackage(chunks=sample_chunks)
        )
    assert result.has_enough_evidence
    assert llm.generate.await_count == 3
    original = llm.generate.await_args_list[1].args[0]
    corrected = llm.generate.await_args_list[2].args[0]
    assert corrected.startswith(original)
    assert corrected.count(sample_chunks[0].text) == 1
    assert "Required JSON schema" in corrected
    assert "PRIVATE_ID" not in corrected and "PRIVATE_CLAIM" not in corrected
    errors = [e for e in logs if e["event"] == "analysis_output_invalid"]
    assert len(errors) == 1 and errors[0]["category"] == category
    if check:
        assert errors[0]["check"] == check
    if "PRIVATE_KEY" in bad:
        assert errors[0]["issues"] == [{"field": "<redacted>", "type": "extra_forbidden"}]
    assert "PRIVATE_" not in json.dumps(logs)
    attempts = [s for s in trace.stages if s["stage"] == "analysis_verdict"]
    assert [s["output_valid"] for s in attempts] == [False, True]
    assert [s["correction"] for s in attempts] == [False, True]


async def test_correction_budget_shared_between_plan_and_verdict(sample_chunks):
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                "bad plan",
                '{"tools":[]}',
                verdict(findings=[]),
            ]
        )
    )
    with pytest.raises(AnalysisOutputError) as error:
        await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))
    assert llm.generate.await_count == 3
    assert error.value.details["analysis_stage"] == "analysis_verdict"


async def test_invalid_tool_input_is_corrected_before_verdict(sample_chunks):
    invalid_plan = json.dumps(
        {
            "tools": [
                {
                    "name": "calculator",
                    "arguments": {
                        "expression": "a",
                        "values": {
                            "a": {
                                "chunk_id": "PRIVATE_ID",
                                "quote": "PRIVATE_QUOTE",
                                "value": "95",
                            }
                        },
                    },
                }
            ]
        }
    )
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                invalid_plan,
                '{"tools":[]}',
                verdict(),
            ]
        )
    )
    with capture_logs() as logs:
        result = await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))
    assert result.has_enough_evidence and not result.tool_results
    error = next(e for e in logs if e["event"] == "analysis_output_invalid")
    assert error["category"] == "tool_validation"
    assert "PRIVATE_" not in json.dumps(logs)


async def test_correcting_verdict_reuses_executed_tool_results(sample_chunks):
    plan = json.dumps(
        {
            "tools": [
                {
                    "name": "calculator",
                    "arguments": {
                        "expression": "a/100",
                        "values": {
                            "a": {
                                "chunk_id": "chunk_1",
                                "quote": "95%",
                                "value": "95",
                            }
                        },
                    },
                }
            ]
        }
    )
    llm = SimpleNamespace(generate=AsyncMock(side_effect=[plan, "bad", verdict()]))
    execute = AnalystTools.execute
    with patch.object(AnalystTools, "execute", autospec=True, side_effect=execute) as spy:
        result = await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))
    spy.assert_called_once()
    assert result.tool_results[0].output["result"] == "0.95"
    assert '"result": "0.95"' in llm.generate.await_args.args[0]


@pytest.mark.parametrize(
    "replies",
    [
        ['{"tools":[]}', "bad", "still bad"],
        ["bad plan", "still bad plan"],
    ],
)
async def test_exhaustion_does_not_retrieve_generate_or_save(sample_chunks, replies):
    llm = SimpleNamespace(generate=AsyncMock(side_effect=replies))
    orchestrator = make_orchestrator(sample_chunks, [])
    orchestrator.analyst = AnalystAgent(llm)
    conversations = SimpleNamespace(save=AsyncMock())
    documents = SimpleNamespace(list_all=AsyncMock(return_value=[]))
    with pytest.raises(AnalysisOutputError):
        await AskQuestionUseCase(orchestrator, conversations, documents).execute("q")
    orchestrator.retriever.retrieve.assert_awaited_once()
    orchestrator.answer_agent.generate.assert_not_awaited()
    orchestrator.answer_agent.review.assert_not_awaited()
    conversations.save.assert_not_awaited()
    assert llm.generate.await_count == len(replies)


async def test_corrected_verdict_still_requires_answer_verification(sample_chunks):
    llm = SimpleNamespace(generate=AsyncMock(side_effect=['{"tools":[]}', "bad", verdict()]))
    orchestrator = make_orchestrator(sample_chunks, [])
    orchestrator.analyst = AnalystAgent(llm)
    result = await orchestrator.process("q")
    assert result["state"] == "answer_ready"
    orchestrator.retriever.retrieve.assert_awaited_once()
    orchestrator.answer_agent.review.assert_awaited_once()


async def test_valid_insufficiency_still_retrieves_more_evidence(sample_chunks):
    llm = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                '{"tools":[]}',
                verdict(has_enough_evidence=False, missing_info="Need Model Y", findings=[]),
                '{"tools":[]}',
                verdict(),
            ]
        )
    )
    orchestrator = make_orchestrator(sample_chunks, [])
    orchestrator.analyst = AnalystAgent(llm)
    result = await orchestrator.process("q")
    assert result["state"] == "answer_ready" and result["loops"] == 1
    assert orchestrator.retriever.retrieve.await_count == 2
    assert "Need Model Y" in orchestrator.retriever.retrieve.await_args.args[0]
    assert llm.generate.await_count == 4


@pytest.mark.parametrize(
    "failure", [LLMRateLimitError("Groq", 60), RuntimeError("PRIVATE_FAILURE")]
)
async def test_provider_or_unexpected_failure_during_correction_propagates(sample_chunks, failure):
    llm = SimpleNamespace(generate=AsyncMock(side_effect=['{"tools":[]}', "bad", failure]))
    with pytest.raises(type(failure)) as error:
        await AnalystAgent(llm).analyze("q", EvidencePackage(chunks=sample_chunks))
    assert error.value is failure and llm.generate.await_count == 3


async def test_correction_usage_includes_invalid_completion(sample_chunks, monkeypatch):
    adapter, create, _ = adapter_with(
        monkeypatch,
        [
            completion(content='{"tools":[]}'),
            completion(content="bad"),
            completion(content=verdict()),
        ],
    )
    with question_scope() as trace:
        result = await AnalystAgent(adapter).analyze("q", EvidencePackage(chunks=sample_chunks))
    assert result.has_enough_evidence and create.await_count == 3
    usage = trace.summary()
    assert usage["llm_calls"] == usage["provider_requests"] == 3
    assert usage["total_tokens"] == 375 and usage["retries"] == 0
    assert [c["stage"] for c in usage["calls"]] == [
        "tool_plan",
        "analysis_verdict",
        "analysis_verdict",
    ]


async def test_empty_evidence_does_not_call_model():
    llm = SimpleNamespace(generate=AsyncMock())
    result = await AnalystAgent(llm).analyze("q", EvidencePackage())
    assert not result.has_enough_evidence
    llm.generate.assert_not_awaited()
