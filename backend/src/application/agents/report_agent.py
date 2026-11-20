import asyncio
import json
from typing import Literal

import structlog
from pydantic import Field, ValidationError, model_validator

from src.application.structured_output import parse_model
from src.domain.entities.analysis import StrictModel
from src.domain.exceptions.llm_provider_error import LLMProviderError
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)
Section = Literal["answer", "analysis", "sources"]
SECTION_ORDER: tuple[Section, ...] = ("answer", "analysis", "sources")


class ReportDesign(StrictModel):
    font: Literal["sans", "serif", "mono"] = "sans"
    page_size: Literal["A4", "Letter"] = "A4"
    columns: Literal[1, 2] = 1
    title_size: int = Field(default=25, ge=18, le=32)
    heading_size: int = Field(default=15, ge=12, le=20)
    body_size: int = Field(default=11, ge=10, le=14)
    accent: str = Field(default="#235B4E", pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: str = Field(default="#1C2622", pattern=r"^#[0-9a-fA-F]{6}$")
    margins: int = Field(default=48, ge=36, le=66)
    spacing: int = Field(default=9, ge=5, le=16)
    line_height: float = Field(default=1.35, ge=1.15, le=1.7)
    heading_style: Literal["bold", "regular"] = "bold"
    title_alignment: Literal["left", "center"] = "left"
    section_order: list[Section] = Field(default_factory=lambda: list(SECTION_ORDER))

    @model_validator(mode="after")
    def readable(self) -> "ReportDesign":
        if sorted(self.section_order) != ["analysis", "answer", "sources"]:
            raise ValueError("Include each section once")
        if not self.title_size > self.heading_size >= self.body_size:
            raise ValueError("Use a clear hierarchy of title, heading and body sizes")
        for color in (self.accent, self.text_color):
            rgb = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
            luminance = sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))
            if 1.05 / (luminance + 0.05) < 4.5:
                raise ValueError("Use text colors with sufficient contrast on white")
        return self


class ReportAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def design(
        self, brief: str, answer_length: int, tools: int, sources: int
    ) -> tuple[ReportDesign, bool]:
        system = (
            "You design professional PDF reports. Return only a JSON object matching this schema: "
            + json.dumps(ReportDesign.model_json_schema())
            + " Honor the reader's design preferences. Colors must have at least 4.5:1 contrast "
            "with white. Use one column for wide tables and detailed analyses. Choose all design "
            "settings freely within the schema. Do not write report content or omit sections."
        )
        prompt = json.dumps(
            {
                "preferences": brief,
                "answer_characters": answer_length,
                "analysis_results": tools,
                "source_count": sources,
            }
        )
        try:
            async with asyncio.timeout(35):
                output = await self.llm.generate(
                    prompt, system, TokenBudget(1024, json_output=True)
                )
            return parse_model(output, ReportDesign), True
        except (LLMProviderError, TimeoutError, ValidationError) as exc:
            logger.info("report_design_defaulted", reason=type(exc).__name__)
            return ReportDesign(), False
