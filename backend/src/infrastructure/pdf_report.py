import re
from functools import cache
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, LongTable, PageTemplate, Paragraph

from src.application.agents.report_agent import ReportDesign
from src.domain.entities.answer import Source

TOOL_LABELS = {
    "calculator": "Calculator",
    "table_extractor": "Table extractor",
    "document_comparison": "Document comparison",
    "data_analysis": "Data analysis",
}


@cache
def report_fonts(family: str) -> tuple[str, str]:
    system_dir = Path("/usr/share/fonts/truetype/dejavu")
    stem = {"sans": "DejaVuSans", "serif": "DejaVuSerif", "mono": "DejaVuSansMono"}[family]
    if not (system_dir / f"{stem}.ttf").is_file():
        base = {"sans": "Helvetica", "serif": "Times-Roman", "mono": "Courier"}[family]
        return base, "Times-Bold" if family == "serif" else f"{base}-Bold"
    for suffix in ("", "-Bold"):
        pdfmetrics.registerFont(TTFont(stem + suffix, str(system_dir / f"{stem}{suffix}.ttf")))
    italic = "Italic" if family == "serif" else "Oblique"
    for suffix, fallback in ((f"-{italic}", ""), (f"-Bold{italic}", "-Bold")):
        path = system_dir / f"{stem}{suffix}.ttf"
        pdfmetrics.registerFont(
            TTFont(
                stem + suffix, str(path if path.is_file() else system_dir / f"{stem}{fallback}.ttf")
            )
        )
    pdfmetrics.registerFontFamily(
        stem,
        normal=stem,
        bold=stem + "-Bold",
        italic=stem + f"-{italic}",
        boldItalic=stem + f"-Bold{italic}",
    )
    return stem, stem + "-Bold"


def safe_text(value: str) -> str:
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)).replace("\n", "<br/>")


def inline_markup(token: Token) -> str:
    tags = {"strong_open": "<b>", "strong_close": "</b>", "em_open": "<i>", "em_close": "</i>"}
    parts = []
    for child in token.children or []:
        if child.type in tags:
            parts.append(tags[child.type])
        elif child.type in {"text", "code_inline", "image"}:
            parts.append(safe_text(child.content))
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" " if child.type == "softbreak" else "<br/>")
    return "".join(parts)


class ReportRenderer:
    def __init__(self, design: ReportDesign, title: str):
        self.design = design
        self.output = BytesIO()
        self.story: list[Flowable] = []
        self.font, bold = report_fonts(design.font)
        self.accent = HexColor(design.accent)
        strong = bold if design.heading_style == "bold" else self.font
        self.body = ParagraphStyle(
            "Body",
            fontName=self.font,
            fontSize=design.body_size,
            leading=design.body_size * design.line_height,
            textColor=HexColor(design.text_color),
            spaceAfter=design.spacing,
        )
        self.heading = ParagraphStyle(
            "Heading",
            parent=self.body,
            fontName=strong,
            fontSize=design.heading_size,
            textColor=self.accent,
            leading=design.heading_size * 1.2,
            keepWithNext=True,
            spaceBefore=design.spacing,
        )
        self.subheading = ParagraphStyle(
            "Subheading",
            parent=self.body,
            fontName=strong,
            keepWithNext=True,
            spaceBefore=design.spacing,
        )
        self.title = ParagraphStyle(
            "Title",
            parent=self.heading,
            fontSize=design.title_size,
            leading=design.title_size * 1.18,
            spaceBefore=0,
            alignment=TA_CENTER if design.title_alignment == "center" else TA_LEFT,
        )
        self.cell = ParagraphStyle("Cell", parent=self.body, fontSize=9, leading=12, spaceAfter=0)
        self.table_header = ParagraphStyle(
            "Table header", parent=self.cell, textColor=white, fontName=bold
        )
        page = A4 if design.page_size == "A4" else letter
        self.doc = BaseDocTemplate(self.output, pagesize=page, title=title, author="Folio")
        margin, gap = design.margins, 18
        self.width = (page[0] - 2 * margin - gap * (design.columns - 1)) / design.columns
        frames = [
            Frame(
                margin + i * (self.width + gap),
                margin,
                self.width,
                page[1] - 2 * margin,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            for i in range(design.columns)
        ]
        self.doc.addPageTemplates(PageTemplate(id="report", frames=frames, onPage=self.footer))
        self.story.append(Paragraph(safe_text(title), self.title))

    def footer(self, canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(self.font, 9)
        canvas.setFillColor(self.accent)
        canvas.drawRightString(doc.pagesize[0] - self.design.margins, 20, f"Folio  /  {doc.page}")
        canvas.restoreState()

    def paragraph(self, text: str, style: ParagraphStyle | None = None) -> None:
        self.story.append(Paragraph(safe_text(text), style or self.body))

    def table(self, rows: list[list[str]], *, formatted: bool = False) -> None:
        if not rows or not rows[0]:
            return
        columns = len(rows[0])
        if columns > (4 if self.design.columns == 2 else 7):
            for row in rows[1:]:
                for label, cell in zip(rows[0], row, strict=True):
                    text = f"{label}: {cell}"
                    if formatted:
                        self.story.append(Paragraph(text, self.body))
                    else:
                        self.paragraph(text)
            return
        cells = [
            [
                Paragraph(
                    cell if formatted else safe_text(cell),
                    self.table_header if i == 0 else self.cell,
                )
                for cell in row
            ]
            for i, row in enumerate(rows)
        ]
        table = LongTable(
            cells,
            colWidths=[self.width / columns] * columns,
            repeatRows=1,
            splitInRow=1,
            hAlign="LEFT",
            spaceAfter=self.design.spacing,
        )
        table.setStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), self.accent),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#F1F4F3")]),
                ("GRID", (0, 0), (-1, -1), 0.35, HexColor("#DAE1DF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
        self.story.append(table)

    def markdown(self, text: str) -> None:
        table: list[list[str]] | None = None
        parent = ""
        for token in MarkdownIt("commonmark", {"html": False}).enable("table").parse(text):
            if token.type == "table_open":
                table = []
            elif token.type == "tr_open" and table is not None:
                table.append([])
            elif token.type == "table_close" and table is not None:
                self.table(table, formatted=True)
                table = None
            elif token.type in {"paragraph_open", "heading_open", "list_item_open"}:
                parent = token.type
            elif token.type == "inline":
                markup = inline_markup(token)
                if table is not None:
                    table[-1].append(markup)
                else:
                    style = self.subheading if parent == "heading_open" else self.body
                    prefix = "• " if token.level >= 3 and parent == "paragraph_open" else ""
                    self.story.append(Paragraph(prefix + markup, style))
            elif token.type in {"fence", "code_block"}:
                self.paragraph(token.content)

    def build(self) -> bytes:
        self.doc.build(self.story)
        return self.output.getvalue()


def render_report(
    design: ReportDesign,
    title: str,
    question: str,
    answer: str,
    sources: list[Source],
    tool_results: list[dict[str, Any]],
) -> bytes:
    report = ReportRenderer(design, title)
    report.paragraph(question)
    for section in design.section_order:
        if section == "answer":
            report.paragraph("Answer", report.heading)
            report.markdown(answer)
        elif section == "sources" and sources:
            report.paragraph("Sources", report.heading)
            for i, source in enumerate(sources, 1):
                location = source["location"] or f"Page {source['page']}"
                subtitle = " · ".join(part for part in (location, source["section"]) if part)
                report.paragraph(f"{i}. {source['document_name']} · {subtitle}", report.subheading)
                report.paragraph(source["quote"])
        elif section == "analysis" and tool_results:
            report.paragraph("Analysis results", report.heading)
            for tool in tool_results:
                report.paragraph(TOOL_LABELS[tool["name"]], report.subheading)
                render_tool_output(report, tool["name"], tool["output"])
    return report.build()


def render_tool_output(report: ReportRenderer, name: str, output: dict[str, Any]) -> None:
    if name == "table_extractor" and output.get("format") == "layout":
        report.paragraph(str(output.get("text", "")))
    elif (
        name == "table_extractor"
        and isinstance(output.get("headers"), list)
        and isinstance(output.get("rows"), list)
    ):
        headers = output["headers"]
        rows = [row for row in output["rows"] if isinstance(row, list) and len(row) == len(headers)]
        report.table([[str(cell) for cell in row] for row in [headers, *rows]])
    elif name == "document_comparison" and isinstance(output.get("rows"), list):
        report.table(
            [
                ["Document", "Aspect", "Evidence"],
                *[
                    [str(row.get(key, "")) for key in ("document_name", "aspect", "evidence")]
                    for row in output["rows"]
                    if isinstance(row, dict)
                ],
            ]
        )
    else:
        for key, value in output.items():
            label = key.replace("_", " ").capitalize()
            if name == "calculator" and key == "inputs" and isinstance(value, dict):
                inputs = ", ".join(f"{variable} = {number}" for variable, number in value.items())
                report.paragraph(f"{label}: {inputs}")
            elif key == "result" and isinstance(value, dict):
                report.table(
                    [
                        ["Value", "Count"],
                        *[[str(item), str(count)] for item, count in value.items()],
                    ]
                )
            elif (
                key == "result"
                and isinstance(value, list)
                and all(isinstance(item, dict) for item in value)
            ):
                report.table(
                    [
                        ["Rank", "Item", "Value"],
                        *[
                            [str(i), str(item.get("label", "")), str(item.get("value", ""))]
                            for i, item in enumerate(value, 1)
                        ],
                    ]
                )
            else:
                report.paragraph(f"{label}: {value}")
