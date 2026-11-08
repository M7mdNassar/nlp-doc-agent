import re
import unicodedata
from collections import Counter
from dataclasses import replace

from src.domain.value_objects.parsed_element import ParsedElement


def clean_elements(elements: list[ParsedElement]) -> list[ParsedElement]:
    """Remove repeated page-edge boilerplate; preserve tables and source locations."""
    edges: Counter[str] = Counter()
    pages: set[int] = set()
    for element in elements:
        if not element.is_table:
            lines = [line.strip() for line in element.text.splitlines() if line.strip()]
            if lines:
                edges.update({lines[0], lines[-1]})
                pages.add(element.page)
    repeated = {
        line
        for line, count in edges.items()
        if len(pages) >= 3
        and count >= max(3, len(pages) * 0.6)
        and len(line) < 160
        and not re.match(r"(?:chapter|section|#)", line, re.I)
    }
    cleaned = []
    for element in elements:
        if element.is_table:
            cleaned.append(element)
            continue
        text = unicodedata.normalize("NFKC", element.text).replace("\x00", "").replace("\u00ad", "")
        lines = text.splitlines()
        for index in {0, len(lines) - 1}:
            if lines and lines[index].strip() in repeated:
                lines[index] = ""
        text = "\n".join(lines)
        text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-z])", "", text)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            cleaned.append(replace(element, text=text))
    return cleaned
