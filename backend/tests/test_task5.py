import json
import shutil
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from src.api.dependencies.providers import get_llm
from src.api.routers import voice
from src.domain.exceptions.llm_provider_error import LLMRateLimitError
from src.infrastructure.parsers.factory import parser_factory
from src.main import create_app

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield app, client


async def test_voice_accepts_audio_and_returns_editable_transcript(client, monkeypatch):
    _, http = client
    service = AsyncMock(return_value="What is the measured latency?")
    monkeypatch.setattr(voice, "transcribe_audio", service)
    response = await http.post("/voice/transcribe", files={"file": ("query.webm", b"clip")})
    assert response.status_code == 200
    assert response.json() == {"text": "What is the measured latency?"}
    service.assert_awaited_once_with(b"clip", "webm")


@pytest.mark.parametrize(
    "filename,data,status",
    [
        ("query.txt", b"text", 400),
        ("query.wav", b"", 400),
        ("query.wav", b"large", 413),
    ],
)
async def test_voice_validates_uploads_before_calling_the_provider(
    client, monkeypatch, filename, data, status
):
    _, http = client
    service = AsyncMock()
    monkeypatch.setattr(voice, "transcribe_audio", service)
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 4)
    response = await http.post("/voice/transcribe", files={"file": (filename, data)})
    assert response.status_code == status
    service.assert_not_awaited()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract required for OCR")
@pytest.mark.parametrize("extension", ["png", "jpg", "webp"])
async def test_image_ocr_produces_citable_ingestion_text(tmp_path, extension):
    path = tmp_path / f"measurement.{extension}"
    image = Image.new("RGB", (800, 200), "white")
    ImageDraw.Draw(image).text(
        (30, 65), "Median latency is 18.6 ms.", font=ImageFont.load_default(size=36), fill="black"
    )
    image.save(path)
    elements = await parser_factory.get_parser(extension).parse(path)
    assert "18.6 ms" in elements[0].text
    assert elements[0].page == 1
    assert elements[0].location == "Image text (OCR)"


async def test_ocr_rejects_disguised_and_oversized_images(tmp_path, monkeypatch):
    from src.infrastructure.parsers import image_parser

    path = tmp_path / "fake.png"
    image = Image.new("RGB", (100, 100))
    image.save(path, "JPEG")
    parser = parser_factory.get_parser("png")
    with pytest.raises(ValueError, match="extension"):
        await parser.parse(path)
    image.save(path, "PNG")
    monkeypatch.setattr(image_parser, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ValueError, match="pixels"):
        await parser.parse(path)


def report_body():
    return {
        "title": "Latency report",
        "design": "Serif, Letter, navy headings and sources first",
        "question": "What is the measured latency?",
        "answer": "**Median latency** was 18.6 ms.\n\n| Model | P95 |\n|---|---|\n| A | 31.4 ms |",
        "sources": [
            {
                "document_id": "doc_1",
                "chunk_id": "chunk_1",
                "document_name": "measure.png",
                "page": 1,
                "section": None,
                "location": "Image text (OCR)",
                "quote": "Median latency is 18.6 ms.",
            }
        ],
        "tool_results": [
            {"name": "data_analysis", "output": {"operation": "mean", "count": 5, "result": "0.88"}}
        ],
    }


async def test_report_route_applies_design_and_preserves_content(client):
    app, http = client
    response_json = json.dumps(
        {
            "font": "serif",
            "page_size": "Letter",
            "accent": "#19365B",
            "section_order": ["sources", "analysis", "answer"],
        }
    )
    llm = AsyncMock()
    llm.generate.return_value = response_json
    app.dependency_overrides[get_llm] = lambda: llm
    response = await http.post("/reports/pdf", json=report_body())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-report-design"] == "agent"
    page = PdfReader(BytesIO(response.content)).pages[0]
    assert page.mediabox.width == 612
    text = page.extract_text()
    assert text.index("Sources") < text.index("Analysis results") < text.index("Answer")
    assert all(
        value in text for value in ["Latency report", "measure.png", "18.6 ms", "31.4 ms", "0.88"]
    )
    assert "measure.png" not in llm.generate.await_args.args[0]


@pytest.mark.parametrize(
    "design_response", ['{"accent":"#FFFFFF"}', "bad JSON", LLMRateLimitError("Groq", 10)]
)
async def test_report_falls_back_to_standard_layout_on_bad_design_or_provider_limit(
    client, design_response
):
    app, http = client
    llm = AsyncMock()
    if isinstance(design_response, Exception):
        llm.generate.side_effect = design_response
    else:
        llm.generate.return_value = design_response
    app.dependency_overrides[get_llm] = lambda: llm
    response = await http.post("/reports/pdf", json=report_body())
    assert response.status_code == 200
    assert response.headers["x-report-design"] == "standard"
    assert "0.88" in PdfReader(BytesIO(response.content)).pages[0].extract_text()
