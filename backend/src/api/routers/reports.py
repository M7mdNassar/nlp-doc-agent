import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import Field, model_validator
from reportlab.platypus.doctemplate import LayoutError

from src.api.dependencies.providers import get_llm
from src.application.agents.report_agent import ReportAgent
from src.core.errors import AppError
from src.domain.entities.analysis import StrictModel
from src.domain.entities.answer import Source
from src.domain.ports.llm import LLMClient
from src.infrastructure.pdf_report import render_report

router = APIRouter()


class ReportTool(StrictModel):
    name: Literal["calculator", "table_extractor", "document_comparison", "data_analysis"]
    output: dict[str, Any] = Field(max_length=30)


class ReportRequest(StrictModel):
    title: str = Field(default="Document analysis report", min_length=1, max_length=120)
    design: str = Field(default="", max_length=1000)
    question: str = Field(min_length=1, max_length=8000)
    answer: str = Field(min_length=1, max_length=64_000)
    sources: list[Source] = Field(min_length=1, max_length=64)
    tool_results: list[ReportTool] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def bound_content(self) -> "ReportRequest":
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("The report must contain at most 256 KiB of content")
        return self


@router.post("/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
async def create_pdf_report(
    report: ReportRequest, llm: Annotated[LLMClient, Depends(get_llm)]
) -> Response:
    design, generated = await ReportAgent(llm).design(
        report.design, len(report.answer), len(report.tool_results), len(report.sources)
    )
    try:
        pdf = await asyncio.to_thread(
            render_report,
            design,
            report.title,
            report.question,
            report.answer,
            report.sources,
            [tool.model_dump() for tool in report.tool_results],
        )
    except LayoutError as exc:
        raise AppError(
            "REPORT_LAYOUT_ERROR",
            "The PDF layout could not fit this report. Try a simpler layout.",
            422,
        ) from exc
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="folio-report.pdf"',
            "Cache-Control": "no-store",
            "X-Report-Design": "agent" if generated else "standard",
        },
    )
