from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from src.core.errors import AppError, ValidationError
from src.infrastructure.llm.transcription import (
    AUDIO_EXTENSIONS,
    MAX_AUDIO_BYTES,
    transcribe_audio,
)

router = APIRouter()


class Transcript(BaseModel):
    text: str


@router.post("/transcribe")
async def transcribe(file: Annotated[UploadFile, File()]) -> Transcript:
    extension = PurePath(file.filename or "").suffix.lower().lstrip(".")
    if extension not in AUDIO_EXTENSIONS:
        raise ValidationError("Use a WAV, WebM, Ogg, MP3, M4A, MP4, or FLAC recording.")
    content = await file.read(MAX_AUDIO_BYTES + 1)
    if not content:
        raise ValidationError("Record a question before transcribing.")
    if len(content) > MAX_AUDIO_BYTES:
        raise AppError("AUDIO_TOO_LARGE", "The recording exceeds 10 MiB.", 413)
    return Transcript(text=await transcribe_audio(content, extension))
