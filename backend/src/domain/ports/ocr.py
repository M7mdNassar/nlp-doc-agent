from pathlib import Path
from typing import Protocol


class OCR(Protocol):
    async def extract_text(self, file_path: Path) -> tuple[str, float]:
        """Returns extracted text and confidence score."""
        ...
