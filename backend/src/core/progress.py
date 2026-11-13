"""Public execution activity: fixed labels only, never prompts or model reasoning."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from src.domain.entities.progress import AgentName, ProgressStep, ToolUsage

STAGES: dict[str, tuple[AgentName, str, str | None]] = {
    "query_rewrite": ("retriever", "Understanding the question", None),
    "retrieval": ("retriever", "Finding relevant passages", None),
    "vector_search": ("retriever", "Hybrid document search", "hybrid_search"),
    "reranking": ("retriever", "Passage reranking", "reranker"),
    "analysis": ("analyst", "Assessing the evidence", None),
    "answer_generation": ("answer", "Writing the answer", None),
    "citation_validation": ("verification", "Citation validation", "citation_validator"),
    "answer_verification": ("verification", "Reviewing answer grounding", None),
}
TOOL_LABELS = {
    "calculator": "Calculator",
    "table_extractor": "Table extraction",
    "document_comparison": "Document comparison",
    "data_analysis": "Data analysis",
}


class ProgressTrace:
    def __init__(self, notify: Callable[[ProgressStep], None] | None = None):
        self.steps: list[ProgressStep] = []
        self.notify = notify

    def start(
        self, name: str, tool_name: object = None, *, waiting: bool = False
    ) -> ProgressStep | None:
        definition = STAGES.get(name)
        if waiting:
            if name in {"tool_plan", "analysis_verdict"}:
                definition = STAGES["analysis"]
            if definition:
                definition = (definition[0], "Waiting for provider capacity", None)
        if name == "analyst_tool" and isinstance(tool_name, str) and tool_name in TOOL_LABELS:
            definition = ("analyst", TOOL_LABELS[tool_name], tool_name)
        if definition is None:
            return None
        agent, label, tool = definition
        step: ProgressStep = {
            "id": f"step_{len(self.steps) + 1}",
            "agent": agent,
            "label": label,
            "kind": "tool" if tool else "agent",
            "status": "running",
            "tool": tool,
        }
        self.steps.append(step)
        self.publish(step)
        return step

    def publish(self, step: ProgressStep) -> None:
        if self.notify:
            self.notify(step.copy())

    def tools(self) -> list[ToolUsage]:
        usage: dict[str, ToolUsage] = {}
        for step in self.steps:
            name = step["tool"]
            if name is None:
                continue
            item = usage.setdefault(
                name,
                {
                    "name": name,
                    "label": step["label"],
                    "agent": step["agent"],
                    "calls": 0,
                    "completed": 0,
                    "failed": 0,
                },
            )
            item["calls"] += 1
            item["completed"] += step["status"] == "completed"
            item["failed"] += step["status"] == "failed"
        return list(usage.values())


_progress: ContextVar[ProgressTrace | None] = ContextVar("public_progress", default=None)


def current_progress() -> ProgressTrace | None:
    return _progress.get()


@contextmanager
def progress_scope(notify: Callable[[ProgressStep], None] | None = None) -> Iterator[ProgressTrace]:
    trace = ProgressTrace(notify)
    token = _progress.set(trace)
    try:
        yield trace
    finally:
        _progress.reset(token)
