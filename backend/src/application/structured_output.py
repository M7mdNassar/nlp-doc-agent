import re

from pydantic import BaseModel


def parse_model[T: BaseModel](text: str, schema: type[T]) -> T:
    stripped = text.strip()
    fenced = re.fullmatch(r"\x60{3}(?:json)?\s*\n?(.*?)\n?\x60{3}", stripped, re.S)
    if fenced:
        stripped = fenced.group(1).strip()
    return schema.model_validate_json(stripped, strict=True)
