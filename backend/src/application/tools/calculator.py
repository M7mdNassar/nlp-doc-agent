from typing import Any

import numexpr

from src.domain.ports.tool import Tool


class Calculator(Tool):
    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Calculates mathematical expressions. Use for averages, percentages, and arithmetic."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression (e.g. '(10 + 20) / 2')",
                }
            },
            "required": ["expression"],
        }

    async def execute(self, **kwargs: Any) -> str:
        expression = kwargs.get("expression", "")
        if not expression:
            return "Math Error: No expression provided."
        try:
            # Use numexpr for safe and fast evaluation without using eval()
            result = numexpr.evaluate(expression).item()
            return str(result)
        except Exception as e:
            return f"Math Error: {e}"
