from typing import Literal, TypedDict

AgentName = Literal["retriever", "analyst", "answer", "verification"]


class ProgressStep(TypedDict):
    id: str
    agent: AgentName
    label: str
    kind: Literal["agent", "tool"]
    status: Literal["running", "completed", "failed"]
    tool: str | None


class ToolUsage(TypedDict):
    name: str
    label: str
    agent: AgentName
    calls: int
    completed: int
    failed: int
