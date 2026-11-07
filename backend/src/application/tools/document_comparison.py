from typing import Any

from src.domain.ports.tool import Tool


class DocumentComparison(Tool):
    @property
    def name(self) -> str:
        return "document_comparison"

    @property
    def description(self) -> str:
        return "Structures evidence to compare multiple documents based on a specific aspect."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "aspect": {
                    "type": "string",
                    "description": "The aspect to compare (e.g., 'accuracy', 'methodology')",
                }
            },
            "required": ["aspect"],
        }

    async def execute(self, **kwargs: Any) -> str:
        aspect = kwargs.get("aspect", "")
        return f"Please analyze the provided context to compare the documents specifically regarding: {aspect}."
