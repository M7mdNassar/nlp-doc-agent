from typing import Any


def validate_table_data(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Table metadata must be an object")
    headers, rows = data.get("headers"), data.get("rows")
    if not isinstance(headers, list) or not all(isinstance(h, str) for h in headers):
        raise ValueError("Table headers must be a list of column names")
    if not isinstance(rows, list) or any(
        not isinstance(row, list) or len(row) != len(headers) for row in rows
    ):
        raise ValueError("Table rows must match the header width")
    if data.get("format") == "layout" and (
        not isinstance(data.get("text"), str) or headers or rows
    ):
        raise ValueError("Layout tables require source text and an empty cell grid")
