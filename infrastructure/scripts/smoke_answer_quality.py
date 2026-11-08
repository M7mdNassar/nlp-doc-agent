"""Optional Groq check using synthetic evidence only; no database or document writes."""

import asyncio
import json

from src.application.agents.answer.answer_agent import AnswerAgent
from src.domain.entities.analysis import AnalysisResult, Finding
from src.domain.entities.answer import AnswerBlock, AnswerDraft, EvidenceReference
from src.domain.entities.chunk import Chunk
from src.domain.entities.evidence import EvidencePackage
from src.domain.value_objects.chunk_id import ChunkId
from src.domain.value_objects.document_id import DocumentId
from src.infrastructure.llm.router import LLMRouter


async def main() -> None:
    source = (
        "A traffic project used overhead drone footage for vehicle detection. "
        "Traffic throughput improved by approximately 0.25 cars/s compared with fixed timing "
        "(simulation-based). A separate classifier reported 91% accuracy on a 40-example "
        "validation set."
    )
    chunk = Chunk(
        id=ChunkId("chunk_quality_check"),
        document_id=DocumentId("doc_quality_check"),
        text=source,
        page=1,
        document_name="Synthetic project report",
    )
    evidence = EvidencePackage(chunks=[chunk])
    analysis = AnalysisResult(True, "", findings=[Finding(text=source, chunk_ids=[str(chunk.id)])])
    agent = AnswerAgent(LLMRouter())
    cases = [
        (
            "omitted_simulation",
            "Traffic throughput improved by approximately 0.25 cars/s compared with fixed timing.",
            False,
        ),
        (
            "invented_input_origin",
            "The throughput improvement was evaluated in simulation "
            "using synthetic traffic data instead of real observations.",
            False,
        ),
        (
            "unsupported_absolute",
            "The throughput evaluation never used any real measurements.",
            False,
        ),
        (
            "preserved_scope",
            "Traffic throughput improved by approximately 0.25 cars/s compared "
            "with fixed timing in simulation. The report does not establish a real-world "
            "deployment measurement.",
            True,
        ),
        (
            "unrelated_fact",
            "The traffic project used overhead drone footage for vehicle detection.",
            True,
        ),
        (
            "invented_deployment",
            "The classifier achieves 91% accuracy in production.",
            False,
        ),
        (
            "validation_scope",
            "The classifier reported 91% accuracy on a 40-example validation set.",
            True,
        ),
    ]
    failures = []
    for name, claim, expected in cases:
        draft = AnswerDraft(
            blocks=[
                AnswerBlock(
                    text=claim,
                    citations=[EvidenceReference(chunk_id=str(chunk.id), quote=source)],
                )
            ]
        )
        actual = await agent.is_grounded(draft, evidence, analysis)
        print(
            json.dumps({"case": name, "expected": expected, "actual": actual}),
            flush=True,
        )
        if actual != expected:
            failures.append(name)
    draft = await agent.generate(
        "Summarize the projects and their reported results.", evidence, analysis
    )
    grounded = await agent.is_grounded(draft, evidence, analysis)
    print(
        json.dumps(
            {
                "case": "generated_summary",
                "grounded": grounded,
                "answer": [block.text for block in draft.blocks],
            }
        ),
        flush=True,
    )
    if not grounded:
        failures.append("generated_summary")
    assert not failures, f"Quality checks failed: {failures}"
    print(json.dumps({"status": "passed", "checks": len(cases) + 1}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
