from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies.providers import get_ask_question_uc
from src.application.use_cases.ask_question import AskQuestionUseCase
from src.domain.entities.answer import ChatResult
from src.domain.value_objects.metadata_filters import MetadataFilters

router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    filters: MetadataFilters | None = None


@router.post("", response_model=None)
async def chat(
    request: ChatRequest, uc: Annotated[AskQuestionUseCase, Depends(get_ask_question_uc)]
) -> ChatResult:
    return await uc.execute(request.message, request.conversation_id, request.filters)
