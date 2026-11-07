from src.domain.ports.tool import Tool


class ToolRegistry:
    def __init__(self) -> None:  # Added -> None
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_available_tools_prompt(self) -> str:
        prompt = "Available Tools:\n"
        for tool in self._tools.values():
            prompt += f"- {tool.name}: {tool.description}\n"
            prompt += f"  Schema: {tool.parameters_schema}\n"
        return prompt
