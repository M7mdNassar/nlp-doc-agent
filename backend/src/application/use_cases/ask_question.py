from src.application.agents.orchestrator.orchestrator import Orchestrator


class AskQuestionUseCase:
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    async def execute(self, question: str) -> dict[str, str | int]:
        return await self.orchestrator.process(question)
