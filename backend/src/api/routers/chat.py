from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies.providers import get_ask_question_uc
from src.application.use_cases.ask_question import AskQuestionUseCase

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("")
async def chat(
    request: ChatRequest,
    uc: Annotated[AskQuestionUseCase, Depends(get_ask_question_uc)],
) -> dict[str, str | int]:
    result = await uc.execute(request.message)
    return result
