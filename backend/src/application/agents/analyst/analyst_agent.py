import json
from dataclasses import dataclass

import structlog

from src.application.tools.registry import ToolRegistry
from src.domain.entities.evidence import EvidencePackage
from src.domain.ports.llm import LLMClient
from src.domain.value_objects.token_budget import TokenBudget

logger = structlog.get_logger(__name__)


@dataclass
class AnalysisResult:
    has_enough_evidence: bool
    missing_info: str


class AnalystAgent:
    def __init__(self, llm: LLMClient, registry: ToolRegistry):
        self.llm = llm
        self.registry = registry

    async def analyze(self, question: str, evidence: EvidencePackage) -> AnalysisResult:
        if evidence.is_empty:
            return AnalysisResult(False, "No documents found.")

        context = ""
        for i, chunk in enumerate(evidence.chunks):
            context += f"[{i}] {chunk.document_id} (p.{chunk.page}): {chunk.text}\n\n"

        tools_desc = self.registry.get_available_tools_prompt()

        system = f"""You are an expert research analyst. Evaluate if the provided context contains enough evidence to answer the user's question.
You have access to the following tools to perform calculations or extract data:

{tools_desc}

Output STRICT JSON only. You can either call a tool OR finish the analysis:
To call a tool:
{{"action": "tool_name", "parameters": {{...}}}}

To finish:
{{"action": "finish", "has_enough_evidence": true/false, "missing_info": "string (if false)"}}
"""

        prompt = f"Question: {question}\n\nContext:\n{context}"

        # Max 3 loops to prevent infinite tool calling
        for _iteration in range(3):
            budget = TokenBudget(max_tokens=300)
            try:
                response = await self.llm.generate(prompt, system, budget)
                clean_json = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)

                action = data.get("action")

                if action == "finish":
                    return AnalysisResult(
                        has_enough_evidence=data.get("has_enough_evidence", False),
                        missing_info=data.get("missing_info", ""),
                    )

                # Execute Tool
                tool = self.registry.get(action)
                if tool:
                    params = data.get("parameters", {})
                    logger.info(f"Analyst executing tool: {action} with {params}")
                    tool_result = await tool.execute(**params)

                    # Append tool result to prompt for the next iteration
                    prompt += f"\n\nTool Result ({action}): {tool_result}\nWhat is your next step?"
                else:
                    prompt += (
                        f"\n\nError: Tool '{action}' not found. Please finish or use a valid tool."
                    )

            except Exception as e:
                logger.error(f"Analyst loop failed: {e}")
                break

        # Fallback if loop exhausts
        return AnalysisResult(False, "Analysis failed to conclude.")
