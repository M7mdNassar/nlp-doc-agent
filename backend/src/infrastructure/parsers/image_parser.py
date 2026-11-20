import asyncio
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from src.core.config import settings
from src.domain.value_objects.parsed_element import ParsedElement

IMAGE_TYPES = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "webp": "WEBP",
}
MAX_IMAGE_PIXELS = 20_000_000


class ImageParser:
    def supports(self, file_type: str) -> bool:
        return file_type.lower() in IMAGE_TYPES

    async def parse(self, file_path: Path) -> list[ParsedElement]:
        return await asyncio.to_thread(self._parse, file_path)

    def _parse(self, path: Path) -> list[ParsedElement]:
        expected = IMAGE_TYPES.get(path.suffix.lower().lstrip("."))
        pixels = BytesIO()
        try:
            with Image.open(path, formats=list(set(IMAGE_TYPES.values()))) as image:
                if image.format != expected:
                    raise ValueError("Image bytes do not match the file extension.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Images must contain no more than 20 million pixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Upload a still image with one frame.")
                oriented = ImageOps.exif_transpose(image).convert("RGBA")
                background = Image.new("RGBA", oriented.size, "white")
                background.alpha_composite(oriented)
                background.convert("L").save(pixels, format="PNG")
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError(
                "Could not read this image. Upload a valid PNG, JPEG, or WebP."
            ) from exc

        try:
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", settings.OCR_LANGUAGES],
                input=pixels.getvalue(),
                capture_output=True,
                check=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise ValueError("Image OCR requires Tesseract on the ingestion worker.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Image OCR timed out. Try a smaller image.") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                "Image OCR failed. Check the worker's Tesseract language packs."
            ) from exc
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("No readable text was found in the image.")
        return [ParsedElement(text, page=1, location="Image text (OCR)")]
